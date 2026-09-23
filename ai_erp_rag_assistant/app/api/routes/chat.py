"""由 LangGraph ERP/RAG 工作流驱动的聊天接口。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from hashlib import sha256
from typing import Annotated, Any, Literal, cast

from fastapi import APIRouter, Depends, Header, HTTPException
from langchain_core.runnables import RunnableConfig
from langsmith import tracing_context
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from ai_erp_rag_assistant.app.agents.workflow_adapter import (
    create_deepagent_workflow,
    model_overrides_key,
)
from ai_erp_rag_assistant.app.api.dependencies import (
    persistent_identity,
    rag_runtime_config,
    verified_access_tags,
    with_header_identity,
)
from ai_erp_rag_assistant.app.assistant_catalog import APPROVAL_ASSISTANT_KEY, assistant_type_for_key
from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.database import get_optional_db_session
from ai_erp_rag_assistant.app.graph.state import ErpRagState, initial_state
from ai_erp_rag_assistant.app.graph.workflow import create_workflow
from ai_erp_rag_assistant.app.api.schemas import ChatRequest, ChatResponse
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event
from ai_erp_rag_assistant.app.services.chat_execution_service import (
    ChatPersistenceError,
    build_chat_response as _chat_response,
    finalize_chat_execution,
    load_cached_chat_response,
    save_chat_exchange,
    workflow_failure_state,
)
from ai_erp_rag_assistant.app.services.execution_repository import (
    ExecutionConflictError,
    execution_request_hash,
    execution_repository,
)
from ai_erp_rag_assistant.app.services.execution_runtime import DurableExecutionContext
from ai_erp_rag_assistant.app.services.langsmith_trace import langsmith_client
from ai_erp_rag_assistant.app.services.session_repository import session_repository


router = APIRouter(tags=["Chat"])
workflow = create_workflow()
stateless_workflow = create_workflow(with_checkpointer=False)


@lru_cache(maxsize=8)
def _deepagent_workflow(
    assistant_type: str,
    with_checkpointer: bool,
    model_overrides_json: str = "{}",
    system_context: str = "",
) -> Any:
    """按助手类型惰性创建 Harness，未启用时不会初始化额外模型。"""
    if assistant_type not in {"rag", "approval"}:
        raise ValueError(f"不支持的助手类型：{assistant_type}")
    return create_deepagent_workflow(
        cast(Literal["rag", "approval"], assistant_type),
        model_overrides=json.loads(model_overrides_json),
        system_context=system_context,
        with_checkpointer=with_checkpointer,
    )


def _selected_workflows(
    orchestrator: str,
    assistant_type: str,
    *,
    model_overrides: dict[str, Any] | None = None,
    system_context: str = "",
) -> tuple[Any, Any]:
    """返回内存会话与持久化会话各自使用的工作流。"""
    if orchestrator == "deepagent":
        return (
            _deepagent_workflow(
                assistant_type,
                True,
                model_overrides_key(model_overrides),
                system_context,
            ),
            _deepagent_workflow(
                assistant_type,
                False,
                model_overrides_key(model_overrides),
                system_context,
            ),
        )
    return workflow, stateless_workflow


def _thread_id(request: ChatRequest, assistant_key: str) -> str:
    """按租户、用户、助手和前端会话生成隔离的工作流线程 ID。"""
    tenant = request.company_id.strip() or "default"
    principal = request.uid.strip() or request.user_id.strip()
    session = request.session_id.strip()
    digest = sha256(
        f"{tenant}\x1f{principal}\x1f{assistant_key}\x1f{session}".encode()
    ).hexdigest()
    return f"erp-rag:{digest}"


def _save_exchange(
    request: ChatRequest,
    assistant_key: str,
    result: ErpRagState,
    response: ChatResponse,
    *,
    enabled: bool,
) -> None:
    """保存会话，并把应用层错误映射为 HTTP 503。"""
    try:
        save_chat_exchange(
            request,
            assistant_key,
            result,
            response,
            session_repository,
            enabled=enabled,
        )
    except ChatPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _sse(event: str, data: Any) -> str:
    """按 SSE 协议编码单个事件，JSON 可安全携带换行和中文。"""
    payload = json.dumps(data, ensure_ascii=False, separators=(",", ":"), default=str)
    return f"event: {event}\ndata: {payload}\n\n"


def _message_chunk_text(chunk: Any) -> str:
    """兼容字符串和 OpenAI 内容块格式，并保留 Token 中的空白。"""
    content = getattr(chunk, "content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for item in content:
        if isinstance(item, str):
            parts.append(item)
        elif isinstance(item, dict):
            parts.append(str(item.get("text") or item.get("content") or ""))
    return "".join(parts)


def _stream_cached_response(
    response: ChatResponse, *, assistant_key: str, session_id: str
) -> Iterator[str]:
    """幂等缓存命中时仍保持流式响应协议。"""
    yield _sse(
        "metadata",
        {
            "assistant_key": assistant_key,
            "assistant_type": response.assistant_type,
            "session_id": session_id,
            "run_id": response.run_id,
            "cached": True,
        },
    )
    yield _sse("final", response.model_dump(mode="json"))
    yield _sse("done", {})


def _cached_exchange_response(
    request: ChatRequest,
    assistant_key: str,
) -> ChatResponse | StreamingResponse | None:
    """读取完成响应，并按原请求的 JSON 或 SSE 传输方式返回。"""
    try:
        response = load_cached_chat_response(
            request,
            assistant_key,
            session_repository,
        )
    except ChatPersistenceError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if response is None:
        return None
    if not request.stream:
        return response
    return StreamingResponse(
        _stream_cached_response(
            response,
            assistant_key=assistant_key,
            session_id=request.session_id,
        ),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _stream_workflow(
    *,
    runtime_workflow: Any,
    state: ErpRagState,
    config: RunnableConfig,
    request: ChatRequest,
    assistant_key: str,
    settings: Any,
    persistent_session: bool,
    durable_execution: DurableExecutionContext | None,
) -> Iterator[str]:
    """执行 Graph 并仅向前端转发最终回答节点产生的 LLM Token。"""
    yield _sse(
        "metadata",
        {
            "assistant_key": assistant_key,
            "assistant_type": state.get("assistant_type", "rag"),
            "session_id": request.session_id,
            "run_id": durable_execution.run_key if durable_execution else "",
            "cached": False,
        },
    )
    result: ErpRagState = state
    execution_error: Exception | None = None
    try:
        client = langsmith_client()
        with tracing_context(
            enabled=client is not None,
            client=client,
            project_name=settings.langsmith_project,
        ):
            # messages 提供模型 Token，values 用于获得最终完整状态和结构化业务字段。
            for mode, value in runtime_workflow.stream(
                state,
                config=config,
                stream_mode=["messages", "values"],
            ):
                if mode == "messages":
                    chunk, metadata = value
                    # Planner、Rerank 也会调用 LLM，它们的内部内容绝不能暴露给用户。
                    if metadata.get("langgraph_node") != "answer_with_llm":
                        continue
                    text = _message_chunk_text(chunk)
                    if text:
                        yield _sse("token", {"content": text})
                elif mode == "values":
                    result = cast(ErpRagState, value)
    except Exception as exc:
        execution_error = exc
        result = workflow_failure_state(state, exc)

    finalized = finalize_chat_execution(result, durable_execution, execution_error)
    result = finalized.state
    response = finalized.response
    execution_error = finalized.error
    try:
        # 必须先完成持久化再发 final，避免前端把未落库回答当作成功结果。
        _save_exchange(
            request,
            assistant_key,
            result,
            response,
            # Durable 失败不能写入 request_id 缓存，否则后续重试无法恢复原 Run。
            enabled=persistent_session
            and (durable_execution is None or execution_error is None),
        )
    except HTTPException as exc:
        yield _sse("error", {"message": str(exc.detail), "errors": [str(exc.detail)]})
        yield _sse("done", {})
        return
    if execution_error is not None:
        yield _sse(
            "error",
            {"message": response.message, "errors": response.errors},
        )
    yield _sse("final", response.model_dump(mode="json"))
    yield _sse("done", {})


@router.post(
    "/chat",
    response_model=ChatResponse,
    responses={
        200: {
            "description": "普通 JSON 响应，或 stream=true 时的 SSE 事件流",
            "content": {"text/event-stream": {"schema": {"type": "string"}}},
        }
    },
)
def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
) -> ChatResponse | StreamingResponse:
    """执行一轮对话，并按配置选择是否持久化状态。"""
    # 认证头优先来自 HTTP 传输层；请求体仅用于兼容非浏览器调用方。
    request = with_header_identity(request, authorization, uid)
    settings = get_settings()
    assistant_key = request.assistant_key.strip() or settings.assistant_key
    assistant_type = assistant_type_for_key(assistant_key)
    # 先用 ERP 身份确定可信租户，再按租户和 assistant_key 读取已发布配置。
    request, persistent_user, resolved_company, persistent_user_id = (
        persistent_identity(request, None, None)
    )
    request = request.model_copy(
        update={"company_id": resolved_company, "user_id": persistent_user_id}
    )
    approval_persistence = False
    if session_repository.enabled and assistant_key == APPROVAL_ASSISTANT_KEY:
        try:
            approval_persistence = session_repository.assistant_available(
                company_id=resolved_company,
                assistant_key=assistant_key,
            )
        except Exception as exc:
            # 返回 False 才表示系统 Assistant 尚未配置；数据库异常不能静默降级为内存执行。
            write_audit_event(
                "session.persistence.approval_unavailable",
                {
                    "company_id": resolved_company,
                    "assistant_key": assistant_key,
                    "error": str(exc)[:300],
                },
            )
            raise HTTPException(
                status_code=503,
                detail=f"无法确认 ERP Durable Execution 配置：{exc}",
            ) from exc
    persistent_session = session_repository.enabled and (
        assistant_type == "rag" or approval_persistence
    )
    if approval_persistence:
        # 缓存检查必须早于新建 Run，兼容升级前已经完成但尚无 Run 记录的审批请求。
        cached_exchange = _cached_exchange_response(request, assistant_key)
        if cached_exchange is not None:
            return cached_exchange
    durable_execution: DurableExecutionContext | None = None
    execution_checkpoint: ErpRagState = {}
    if approval_persistence:
        try:
            # ERP Agent 的 request_id 同时承担 Run 幂等键；同一次重试必须保持不变。
            claim = execution_repository.claim_run(
                company_id=resolved_company,
                assistant_key=assistant_key,
                session_key=request.session_id,
                user_id=request.user_id,
                request_id=request.request_id,
                request_hash=execution_request_hash(request, assistant_key),
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except ExecutionConflictError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except Exception as exc:
            write_audit_event(
                "execution.claim.error",
                {
                    "company_id": resolved_company,
                    "assistant_key": assistant_key,
                    "session_id": request.session_id,
                    "request_id": request.request_id,
                    "error": str(exc)[:300],
                },
            )
            raise HTTPException(
                status_code=503,
                detail=f"ERP Durable Execution 不可用：{exc}",
            ) from exc
        execution_checkpoint = cast(ErpRagState, claim.checkpoint_state)
        durable_execution = claim.context
        if claim.completed_response is not None:
            # Run 已完成但聊天消息可能因上次进程退出尚未落库，先补写再返回。
            completed_response = ChatResponse.model_validate(claim.completed_response)
            _save_exchange(
                request,
                assistant_key,
                execution_checkpoint,
                completed_response,
                enabled=True,
            )
            if request.stream:
                return StreamingResponse(
                    _stream_cached_response(
                        completed_response,
                        assistant_key=assistant_key,
                        session_id=request.session_id,
                    ),
                    media_type="text/event-stream",
                    headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
                )
            return completed_response
    # 工作流只使用服务端从 ERP 身份整理出的权限标签，不采信请求体权限字段。
    persistent_user = {
        **persistent_user,
        "rag_access_tags": verified_access_tags(persistent_user),
    }
    rag_runtime = None
    if assistant_type == "rag":
        try:
            rag_runtime = rag_runtime_config(
                db,
                company_id=resolved_company,
                knowledge_base_key="",
                assistant_key=assistant_key,
            )
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        except PermissionError as exc:
            raise HTTPException(status_code=403, detail=str(exc)) from exc
        except RuntimeError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
    if persistent_session and not approval_persistence:
        # RAG 先校验当前发布配置，再允许返回历史幂等响应。
        cached_exchange = _cached_exchange_response(request, assistant_key)
        if cached_exchange is not None:
            return cached_exchange
    # RAG Assistant 的已发布 Prompt/模型配置要在创建 DeepAgent 前注入；
    # LangGraph 模式仍通过 RunnableConfig 使用同一份 runtime。缓存命中已经提前返回，
    # 因此无效请求不会因为初始化模型失败而遮蔽可直接返回的历史结果。
    memory_workflow, persistent_workflow = _selected_workflows(
        settings.orchestrator,
        assistant_type,
        model_overrides=rag_runtime.model_overrides if rag_runtime else None,
        system_context=rag_runtime.system_context if rag_runtime else "",
    )
    thread_id = _thread_id(request, assistant_key)
    config: RunnableConfig = {
        # 运行时对象仅在本次 Graph 调用中传递，避免把 Prompt 和模型参数写入会话存储。
        "configurable": {
            "thread_id": thread_id,
            "rag_runtime": rag_runtime,
            "assistant_type": assistant_type,
            # 该对象只存在于本次进程调用中，持久化内容由仓储自行脱敏。
            "durable_execution": durable_execution,
        },
        "run_name": "erp-rag-chat",
        "tags": ["ai-erp-rag-assistant"],
        "metadata": {
            "thread_id": thread_id,
            "transport": "fastapi",
            "assistant_key": assistant_key,
            "assistant_type": assistant_type,
            "run_id": durable_execution.run_key if durable_execution else "",
            "retrieval_scope": (
                rag_runtime.retrieval_scope if rag_runtime else "disabled"
            ),
        },
    }
    prior: ErpRagState = {}
    if not request.reset:
        # MySQL 与内存 Checkpointer 二选一，避免同一会话出现两个状态真相源。
        if persistent_session:
            try:
                prior = cast(
                    ErpRagState,
                    session_repository.load_state(
                        company_id=request.company_id,
                        assistant_key=assistant_key,
                        user_id=request.user_id,
                        session_key=request.session_id,
                    ),
                )
            except Exception as exc:
                write_audit_event(
                    "session.persistence.read_error",
                    {
                        "company_id": request.company_id,
                        "assistant_key": assistant_key,
                        "session_id": request.session_id,
                        "request_id": request.request_id,
                        "operation": "load_state",
                        "error": str(exc)[:300],
                    },
                )
                raise HTTPException(status_code=503, detail=f"会话持久化不可用：{exc}") from exc
        else:
            snapshot = memory_workflow.get_state(config)
            if snapshot and snapshot.values:
                prior = cast(ErpRagState, dict(snapshot.values))
    if execution_checkpoint:
        # 同一 request_id 恢复时，Run 检查点比上一轮会话状态更新。
        prior = cast(ErpRagState, {**prior, **execution_checkpoint})

    state = initial_state(
        request.session_id,
        request.user_id,
        request.message,
        assistant_type=assistant_type,
        uid=request.uid,
        authorization=request.authorization,
        company_id=request.company_id,
        department=request.department,
        confirm=request.confirm,
        confirm_preview_id=request.preview_id,
        confirm_preview_version=request.preview_version,
        confirm_preview_hash=request.preview_hash,
        selected_template_id=request.selected_template_id,
        form_values=request.form_values,
        selected_assignees=request.selected_assignees,
        prior=prior,
    )
    # 复用已验证身份，避免工作流首节点对同一次请求重复调用 ERP userinfo。
    state["user_context"] = persistent_user
    if durable_execution is not None:
        state.update(
            {
                "execution_run_id": durable_execution.run_key,
                "execution_status": "running",
                "execution_retry_count": durable_execution.retry_count,
                "execution_current_step": durable_execution.current_step,
            }
        )
    # 长期会话使用无 Checkpointer Graph；其他助手继续使用进程内会话状态。
    runtime_workflow = persistent_workflow if persistent_session else memory_workflow
    if request.stream:
        return StreamingResponse(
            _stream_workflow(
                runtime_workflow=runtime_workflow,
                state=state,
                config=config,
                request=request,
                assistant_key=assistant_key,
                settings=settings,
                persistent_session=persistent_session,
                durable_execution=durable_execution,
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    execution_error: Exception | None = None
    try:
        client = langsmith_client()
        with tracing_context(
            enabled=client is not None,
            client=client,
            project_name=settings.langsmith_project,
        ):
            result = runtime_workflow.invoke(state, config=config)
    except Exception as exc:
        execution_error = exc
        # 将失败明确返回给调用方，不能用看似正常的伪造答案掩盖异常。
        result = workflow_failure_state(state, exc)

    finalized = finalize_chat_execution(
        cast(ErpRagState, result),
        durable_execution,
        execution_error,
    )
    _save_exchange(
        request,
        assistant_key,
        finalized.state,
        finalized.response,
        enabled=persistent_session
        and (durable_execution is None or finalized.error is None),
    )
    return finalized.response

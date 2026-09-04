"""由 LangGraph ERP/RAG 工作流驱动的聊天接口。"""

from __future__ import annotations

import json
from collections.abc import Iterator
from functools import lru_cache
from hashlib import sha256
from typing import Annotated, Any, cast

import langsmith.anonymizer as langsmith_anonymizer
from fastapi import APIRouter, Depends, Header, HTTPException
from langchain_core.runnables import RunnableConfig
from langsmith import Client, tracing_context
from sqlalchemy.orm import Session
from starlette.responses import StreamingResponse

from ai_erp_rag_assistant.app import api as api_module
from ai_erp_rag_assistant.app.assistant_catalog import assistant_type_for_key
from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.database import get_optional_db_session
from ai_erp_rag_assistant.app.graph.state import ErpRagState, initial_state
from ai_erp_rag_assistant.app.graph.workflow import create_workflow
from ai_erp_rag_assistant.app.schemas import ChatRequest, ChatResponse
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event
from ai_erp_rag_assistant.app.services.session_repository import session_repository


router = APIRouter(tags=["Chat"])
workflow = create_workflow()
stateless_workflow = create_workflow(with_checkpointer=False)

_SENSITIVE_TRACE_FIELDS = {
    "api_key",
    "authorization",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "token",
}


def _identity_anonymizer(data: Any) -> Any:
    return data


# 旧版 LangSmith 可能没有 create_secret_anonymizer，但两种版本都启用字段级脱敏。
_secret_anonymizer_factory: Any = getattr(
    langsmith_anonymizer, "create_secret_anonymizer", None
)
_secret_anonymizer = (
    _secret_anonymizer_factory()
    if callable(_secret_anonymizer_factory)
    else _identity_anonymizer
)
_field_anonymizer = langsmith_anonymizer.create_anonymizer(
    lambda value, path: (
        "[REDACTED]"
        if path and str(path[-1]).lower() in _SENSITIVE_TRACE_FIELDS
        else value
    ),
    max_depth=24,
)


def _anonymize_trace(data: Any) -> Any:
    return _field_anonymizer(_secret_anonymizer(data))


@lru_cache(maxsize=1)
def _langsmith_client() -> Client | None:
    settings = get_settings()
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return None
    return Client(api_key=settings.langsmith_api_key, anonymizer=_anonymize_trace)


def _thread_id(request: ChatRequest, assistant_key: str) -> str:
    """按租户、用户、助手和前端会话生成隔离的工作流线程 ID。"""
    tenant = request.company_id.strip() or "default"
    principal = request.uid.strip() or request.user_id.strip()
    session = request.session_id.strip()
    digest = sha256(
        f"{tenant}\x1f{principal}\x1f{assistant_key}\x1f{session}".encode()
    ).hexdigest()
    return f"erp-rag:{digest}"


def _chat_response(result: ErpRagState) -> ChatResponse:
    """把内部工作流状态转换为稳定的前端响应。"""
    erp_data = result.get("erp_data", {})
    assistant_type = result.get("assistant_type", "rag")
    if assistant_type not in {"approval", "rag"}:
        assistant_type = "rag"
    return ChatResponse(
        message=result.get("assistant_message", ""),
        route=result.get("route", "unknown"),
        assistant_type=assistant_type,
        plan=result.get("plan", {}),
        tool_calls=result.get("tool_calls", []),
        evidence=result.get("evidence", []),
        citations=api_module.model_service.build_citations(result.get("evidence", [])),
        erp_data=erp_data,
        form_schema=result.get("form_schema") or None,
        preview=result.get("preview") or None,
        errors=result.get("errors", []),
        pending_question=result.get("pending_question", ""),
        workflow_status=str(result.get("workflow_status") or "idle"),
        erp_mode=str(
            erp_data.get("erp_mode")
            or result.get("user_context", {}).get("erp_mode")
            or get_settings().erp_mode
        ),
        erp_write_mode=str(
            erp_data.get("erp_write_mode") or get_settings().erp_write_mode
        ),
    )


def _save_exchange(
    request: ChatRequest,
    assistant_key: str,
    result: ErpRagState,
    response: ChatResponse,
    *,
    enabled: bool,
) -> None:
    """在完整回答生成后保存一轮会话；流式 Token 不单独入库。"""
    if not enabled:
        return
    try:
        session_repository.save_exchange(
            company_id=request.company_id,
            assistant_key=assistant_key,
            session_key=request.session_id,
            user_id=request.user_id,
            erp_uid=request.uid,
            request_id=request.request_id,
            user_message=request.message,
            state=dict(result),
            response=response.model_dump(),
        )
    except Exception as exc:
        write_audit_event(
            "session.persistence.error",
            {
                "company_id": request.company_id,
                "assistant_key": assistant_key,
                "session_id": request.session_id,
                "request_id": request.request_id,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(status_code=503, detail=f"会话持久化失败：{exc}") from exc


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
            "cached": True,
        },
    )
    yield _sse("final", response.model_dump(mode="json"))
    yield _sse("done", {})


def _stream_workflow(
    *,
    runtime_workflow: Any,
    state: ErpRagState,
    config: RunnableConfig,
    request: ChatRequest,
    assistant_key: str,
    settings: Any,
    persistent_session: bool,
) -> Iterator[str]:
    """执行 Graph 并仅向前端转发最终回答节点产生的 LLM Token。"""
    yield _sse(
        "metadata",
        {
            "assistant_key": assistant_key,
            "assistant_type": state.get("assistant_type", "rag"),
            "session_id": request.session_id,
            "cached": False,
        },
    )
    result: ErpRagState = state
    execution_error = ""
    try:
        client = _langsmith_client()
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
        execution_error = str(exc)
        result = {
            **state,
            "assistant_message": f"执行失败：{exc}",
            "errors": [str(exc)],
            "tool_calls": [{"tool": "system.error", "error": str(exc)}],
        }

    response = _chat_response(result)
    try:
        # 必须先完成持久化再发 final，避免前端把未落库回答当作成功结果。
        _save_exchange(
            request,
            assistant_key,
            result,
            response,
            enabled=persistent_session,
        )
    except HTTPException as exc:
        yield _sse("error", {"message": str(exc.detail), "errors": [str(exc.detail)]})
        yield _sse("done", {})
        return
    if execution_error:
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
    request = api_module._with_header_identity(request, authorization, uid)
    settings = get_settings()
    assistant_key = request.assistant_key.strip() or settings.assistant_key
    assistant_type = assistant_type_for_key(assistant_key)
    persistent_session = session_repository.enabled and assistant_type == "rag"
    # 先用 ERP 身份确定可信租户，再按租户和 assistant_key 读取已发布配置。
    request, persistent_user, resolved_company, persistent_user_id = (
        api_module._persistent_identity(request, None, None)
    )
    request = request.model_copy(
        update={"company_id": resolved_company, "user_id": persistent_user_id}
    )
    # 工作流只使用服务端从 ERP 身份整理出的权限标签，不采信请求体权限字段。
    persistent_user = {
        **persistent_user,
        "rag_access_tags": api_module._verified_access_tags(persistent_user),
    }
    rag_runtime = None
    if assistant_type == "rag":
        try:
            rag_runtime = api_module._rag_runtime_config(
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
    if persistent_session:
        # 长期会话必须先用 ERP 身份锁定租户和用户，再检查 request_id 幂等缓存。
        try:
            cached = session_repository.cached_response(
                company_id=resolved_company,
                assistant_key=assistant_key,
                user_id=request.user_id,
                session_key=request.session_id,
                request_id=request.request_id,
            )
        except Exception as exc:
            write_audit_event(
                "session.persistence.read_error",
                {
                    "company_id": request.company_id,
                    "assistant_key": assistant_key,
                    "session_id": request.session_id,
                    "request_id": request.request_id,
                    "operation": "cached_response",
                    "error": str(exc)[:300],
                },
            )
            raise HTTPException(status_code=503, detail=f"会话持久化不可用：{exc}") from exc
        if cached:
            cached_response = ChatResponse.model_validate(cached)
            if request.stream:
                return StreamingResponse(
                    _stream_cached_response(
                        cached_response,
                        assistant_key=assistant_key,
                        session_id=request.session_id,
                    ),
                    media_type="text/event-stream",
                    headers={
                        "Cache-Control": "no-cache",
                        "X-Accel-Buffering": "no",
                    },
                )
            return cached_response

    thread_id = _thread_id(request, assistant_key)
    config: RunnableConfig = {
        # 运行时对象仅在本次 Graph 调用中传递，避免把 Prompt 和模型参数写入会话存储。
        "configurable": {
            "thread_id": thread_id,
            "rag_runtime": rag_runtime,
            "assistant_type": assistant_type,
        },
        "run_name": "erp-rag-chat",
        "tags": ["ai-erp-rag-assistant"],
        "metadata": {
            "thread_id": thread_id,
            "transport": "fastapi",
            "assistant_key": assistant_key,
            "assistant_type": assistant_type,
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
            snapshot = workflow.get_state(config)
            if snapshot and snapshot.values:
                prior = cast(ErpRagState, dict(snapshot.values))

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
        form_values=request.form_values,
        selected_assignees=request.selected_assignees,
        prior=prior,
    )
    # 复用已验证身份，避免工作流首节点对同一次请求重复调用 ERP userinfo。
    state["user_context"] = persistent_user
    # 长期会话使用无 Checkpointer Graph；其他助手继续使用进程内会话状态。
    runtime_workflow = stateless_workflow if persistent_session else workflow
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
            ),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    try:
        client = _langsmith_client()
        with tracing_context(
            enabled=client is not None,
            client=client,
            project_name=settings.langsmith_project,
        ):
            result = runtime_workflow.invoke(state, config=config)
    except Exception as exc:
        # 将失败明确返回给调用方，不能用看似正常的伪造答案掩盖异常。
        result = {
            **state,
            "assistant_message": f"执行失败：{exc}",
            "errors": [str(exc)],
            "tool_calls": [{"tool": "system.error", "error": str(exc)}],
        }

    response = _chat_response(cast(ErpRagState, result))
    _save_exchange(
        request,
        assistant_key,
        cast(ErpRagState, result),
        response,
        enabled=persistent_session,
    )
    return response

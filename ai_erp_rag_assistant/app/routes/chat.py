"""由 LangGraph ERP/RAG 工作流驱动的聊天接口。"""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from typing import Any, cast

import langsmith.anonymizer as langsmith_anonymizer
from fastapi import APIRouter, Header
from langchain_core.runnables import RunnableConfig
from langsmith import Client, tracing_context

from ai_erp_rag_assistant.app import api as api_module
from ai_erp_rag_assistant.app.config import get_settings
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


def _thread_id(request: ChatRequest) -> str:
    tenant = request.company_id.strip() or "default"
    principal = request.uid.strip() or request.user_id.strip()
    session = request.session_id.strip()
    digest = sha256(f"{tenant}\x1f{principal}\x1f{session}".encode()).hexdigest()
    return f"erp-rag:{digest}"


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> ChatResponse:
    """执行一轮对话，并按配置选择是否持久化状态。"""
    # 认证头优先来自 HTTP 传输层；请求体仅用于兼容非浏览器调用方。
    if authorization or uid:
        request = request.model_copy(
            update={
                "authorization": request.authorization or authorization or "",
                "uid": request.uid or uid or "",
            }
        )
    settings = get_settings()
    assistant_key = request.assistant_key.strip() or settings.assistant_key
    persistent_user: dict[str, Any] = {}
    if session_repository.enabled:
        # 长期会话必须先用 ERP 身份锁定租户和用户，再检查 request_id 幂等缓存。
        request, persistent_user, resolved_company, persistent_user_id = (
            api_module._persistent_identity(request, None, None)
        )
        request = request.model_copy(
            update={"company_id": resolved_company, "user_id": persistent_user_id}
        )
        cached = session_repository.cached_response(
            company_id=resolved_company,
            assistant_key=assistant_key,
            user_id=request.user_id,
            session_key=request.session_id,
            request_id=request.request_id,
        )
        if cached:
            return ChatResponse.model_validate(cached)

    thread_id = _thread_id(request)
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "run_name": "erp-rag-chat",
        "tags": ["ai-erp-rag-assistant"],
        "metadata": {"thread_id": thread_id, "transport": "fastapi"},
    }
    prior: ErpRagState = {}
    if not request.reset:
        # MySQL 与内存 Checkpointer 二选一，避免同一会话出现两个状态真相源。
        if session_repository.enabled:
            prior = cast(
                ErpRagState,
                session_repository.load_state(
                    company_id=request.company_id,
                    assistant_key=assistant_key,
                    user_id=request.user_id,
                    session_key=request.session_id,
                ),
            )
        else:
            snapshot = workflow.get_state(config)
            if snapshot and snapshot.values:
                prior = cast(ErpRagState, dict(snapshot.values))

    state = initial_state(
        request.session_id,
        request.user_id,
        request.message,
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
    if persistent_user:
        # 复用已验证身份，避免工作流首节点对同一次请求重复调用 ERP userinfo。
        state["user_context"] = persistent_user

    try:
        client = _langsmith_client()
        with tracing_context(
            enabled=client is not None,
            client=client,
            project_name=settings.langsmith_project,
        ):
            # MySQL 模式由 Repository 持久化状态，因此使用无 Checkpointer 的工作流实例。
            runtime_workflow = (
                stateless_workflow if session_repository.enabled else workflow
            )
            result = runtime_workflow.invoke(state, config=config)
    except Exception as exc:
        # 将失败明确返回给调用方，不能用看似正常的伪造答案掩盖异常。
        result = {
            **state,
            "assistant_message": f"执行失败：{exc}",
            "errors": [str(exc)],
            "tool_calls": [{"tool": "system.error", "error": str(exc)}],
        }

    erp_data = result.get("erp_data", {})
    # 将内部工作流状态收敛为稳定的前端响应契约，不暴露认证和恢复字段。
    response = ChatResponse(
        message=result.get("assistant_message", ""),
        route=result.get("route", "unknown"),
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
    if session_repository.enabled:
        try:
            # 只在工作流完成后原子保存用户消息、回复、状态、预览和工具事件。
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
            from fastapi import HTTPException

            raise HTTPException(status_code=503, detail=f"会话持久化失败：{exc}") from exc
    return response

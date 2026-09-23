"""聊天工作流结果、Durable Execution 和会话持久化编排。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from ai_erp_rag_assistant.app.api.schemas import ChatRequest, ChatResponse
from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.graph.state import ErpRagState
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event
from ai_erp_rag_assistant.app.services.execution_runtime import DurableExecutionContext
from ai_erp_rag_assistant.app.services.model_service import model_service


PUBLIC_CHAT_ERROR = "执行失败，请稍后重试"


class ChatPersistenceError(RuntimeError):
    """会话仓储不可用时抛出的稳定应用层错误。"""


@dataclass(frozen=True)
class ChatExecutionResult:
    """工作流执行完成后的统一状态，供 JSON 和 SSE 传输复用。"""

    state: ErpRagState
    response: ChatResponse
    error: Exception | None


def build_chat_response(result: ErpRagState) -> ChatResponse:
    """把内部工作流状态转换为稳定的前端响应。"""
    erp_data = result.get("erp_data", {})
    assistant_type = result.get("assistant_type", "rag")
    if assistant_type not in {"approval", "rag"}:
        assistant_type = "rag"
    tool_calls = result.get("tool_calls", [])
    failed = (
        result.get("workflow_status") == "failed"
        or result.get("execution_status") == "failed"
        or any(call.get("tool") == "system.error" for call in tool_calls)
    )
    if failed:
        # 原始异常只进入审计和 Durable 状态，不能通过 API 泄漏基础设施信息。
        tool_calls = [
            {**call, "error": PUBLIC_CHAT_ERROR} if call.get("error") else call
            for call in tool_calls
        ]
    return ChatResponse(
        message=PUBLIC_CHAT_ERROR if failed else result.get("assistant_message", ""),
        route=result.get("route", "unknown"),
        assistant_type=assistant_type,
        plan=result.get("plan", {}),
        tool_calls=tool_calls,
        evidence=result.get("evidence", []),
        citations=result.get("citations")
        or model_service.build_citations(result.get("evidence", [])),
        erp_data=erp_data,
        form_schema=result.get("form_schema") or None,
        preview=result.get("preview") or None,
        errors=[PUBLIC_CHAT_ERROR] if failed else result.get("errors", []),
        pending_question=result.get("pending_question", ""),
        workflow_status=str(result.get("workflow_status") or "idle"),
        run_id=str(result.get("execution_run_id") or ""),
        execution_status=str(result.get("execution_status") or ""),
        execution_retry_count=int(result.get("execution_retry_count") or 0),
        execution_current_step=str(result.get("execution_current_step") or ""),
        template_selection_required=bool(
            result.get("template_selection_required")
            or (
                result.get("template_candidates")
                and not (result.get("template") or {}).get("template_id")
            )
        ),
        template_candidates=result.get("template_candidates", []),
        erp_mode=str(
            erp_data.get("erp_mode")
            or result.get("user_context", {}).get("erp_mode")
            or get_settings().erp_mode
        ),
        erp_write_mode=str(
            erp_data.get("erp_write_mode") or get_settings().erp_write_mode
        ),
    )


def workflow_failure_state(state: ErpRagState, error: Exception) -> ErpRagState:
    """将工作流异常转换为可持久化状态，公开响应会再次进行脱敏。"""
    return {
        **state,
        "assistant_message": f"执行失败：{error}",
        "errors": [str(error)],
        "tool_calls": [{"tool": "system.error", "error": str(error)}],
    }


def _execution_fields(
    state: ErpRagState,
    context: DurableExecutionContext | None,
    status: str,
) -> ErpRagState:
    """写入稳定运行字段，但不把仓储控制器放进业务状态。"""
    if context is None:
        return state
    return {
        **state,
        "execution_run_id": context.run_key,
        "execution_status": status,
        "execution_retry_count": context.retry_count,
        "execution_current_step": context.current_step,
    }


def _fail_execution(
    context: DurableExecutionContext | None,
    state: ErpRagState,
    error: Exception,
) -> None:
    """尽力记录运行失败；持久化异常不能覆盖原始业务异常。"""
    if context is None:
        return
    try:
        context.fail(dict(state), error)
    except Exception as persistence_error:
        write_audit_event(
            "execution.persistence.error",
            {
                "run_id": context.run_key,
                "operation": "fail_run",
                "error": str(persistence_error)[:300],
            },
        )


def finalize_chat_execution(
    state: ErpRagState,
    context: DurableExecutionContext | None,
    error: Exception | None,
) -> ChatExecutionResult:
    """统一完成 JSON/SSE 的运行状态和 Durable Run 持久化。"""
    status = "failed" if error is not None else "completed"
    state = _execution_fields(state, context, status)
    if error is not None:
        _fail_execution(context, state, error)
    response = build_chat_response(state)

    if context is not None and error is None:
        try:
            # Run 结果先于聊天消息落库，消息保存失败时可用同一 request_id 补写。
            context.complete(dict(state), response.model_dump(mode="json"))
        except Exception as persistence_error:
            error = persistence_error
            state = {
                **_execution_fields(state, context, "failed"),
                "assistant_message": (
                    "执行结果持久化失败，请使用相同 request_id 重试："
                    f"{persistence_error}"
                ),
                "errors": [*state.get("errors", []), str(persistence_error)],
            }
            _fail_execution(context, state, persistence_error)
            response = build_chat_response(state)
    return ChatExecutionResult(state=state, response=response, error=error)


def load_cached_chat_response(
    request: ChatRequest,
    assistant_key: str,
    repository: Any,
) -> ChatResponse | None:
    """从会话仓储读取已完成响应，不处理具体 HTTP 传输格式。"""
    try:
        cached = repository.cached_response(
            company_id=request.company_id,
            assistant_key=assistant_key,
            user_id=request.user_id,
            session_key=request.session_id,
            request_id=request.request_id,
        )
    except Exception as error:
        write_audit_event(
            "session.persistence.read_error",
            {
                "company_id": request.company_id,
                "assistant_key": assistant_key,
                "session_id": request.session_id,
                "request_id": request.request_id,
                "operation": "cached_response",
                "error": str(error)[:300],
            },
        )
        raise ChatPersistenceError("会话持久化不可用，请稍后重试") from error
    return ChatResponse.model_validate(cached) if cached else None


def save_chat_exchange(
    request: ChatRequest,
    assistant_key: str,
    result: ErpRagState,
    response: ChatResponse,
    repository: Any,
    *,
    enabled: bool,
) -> None:
    """完整回答生成后保存一轮会话；流式 Token 不单独入库。"""
    if not enabled:
        return
    try:
        repository.save_exchange(
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
    except Exception as error:
        write_audit_event(
            "session.persistence.error",
            {
                "company_id": request.company_id,
                "assistant_key": assistant_key,
                "session_id": request.session_id,
                "request_id": request.request_id,
                "error": str(error)[:300],
            },
        )
        raise ChatPersistenceError("会话持久化失败，请稍后重试") from error

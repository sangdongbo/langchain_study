from __future__ import annotations

from hashlib import sha256
from typing import Any

from fastapi import APIRouter, Header

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.graph.state import ErpRagState, initial_state
from ai_erp_rag_assistant.app.graph.workflow import create_workflow
from ai_erp_rag_assistant.app.schemas import ChatRequest, ChatResponse


router = APIRouter(prefix="/api")
workflow = create_workflow()


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
    if authorization or uid:
        request = request.model_copy(update={
            "authorization": request.authorization or authorization or "",
            "uid": request.uid or uid or "",
        })
    config = {"configurable": {"thread_id": _thread_id(request)}}
    prior: ErpRagState = {}
    if not request.reset:
        snapshot = workflow.get_state(config)
        if snapshot and snapshot.values:
            prior = dict(snapshot.values)
    state = initial_state(
        request.session_id,
        request.user_id,
        request.message,
        uid=request.uid,
        authorization=request.authorization,
        company_id=request.company_id,
        department=request.department,
        confirm=request.confirm,
        prior=prior,
    )
    try:
        result = workflow.invoke(state, config=config)
    except Exception as exc:
        # Keep the failure visible in the demo instead of returning a fake answer.
        result = {
            **state,
            "assistant_message": f"执行失败：{exc}",
            "errors": [str(exc)],
            "tool_calls": [{"tool": "system.error", "error": str(exc)}],
        }
    erp_data = result.get("erp_data", {})
    return ChatResponse(
        message=result.get("assistant_message", ""),
        route=result.get("route", "unknown"),
        plan=result.get("plan", {}),
        tool_calls=result.get("tool_calls", []),
        evidence=result.get("evidence", []),
        erp_data=erp_data,
        preview=result.get("preview") or None,
        errors=result.get("errors", []),
        pending_question=result.get("pending_question", ""),
        erp_mode=str(erp_data.get("erp_mode") or result.get("user_context", {}).get("erp_mode") or get_settings().erp_mode),
        erp_write_mode=str(erp_data.get("erp_write_mode") or get_settings().erp_write_mode),
    )

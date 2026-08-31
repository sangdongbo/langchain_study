"""Long-term session read endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from ai_erp_rag_assistant.app import api as api_module
from ai_erp_rag_assistant.app.api_dependencies import persistent_identity
from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.schemas import SessionListRequest, SessionMessagesRequest
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event
from ai_erp_rag_assistant.app.services.session_repository import session_repository


router = APIRouter(tags=["Sessions"])


@router.post("/sessions/list")
def session_list(
    request: SessionListRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """Return sessions scoped to the verified ERP user and company."""
    if not session_repository.enabled:
        raise HTTPException(status_code=503, detail="长期会话未启用，请配置 AI_ERP_SESSION_STORE=mysql")
    request, _, company_id, user_id = api_module._persistent_identity(
        request, authorization, uid
    )
    assistant_key = request.assistant_key.strip() or get_settings().assistant_key
    try:
        items, has_more = session_repository.list_sessions(
            company_id=company_id,
            assistant_key=assistant_key,
            user_id=user_id,
            status=request.status,
            page=request.page,
            page_size=request.page_size,
        )
        return {
            "items": items,
            "count": len(items),
            "page": request.page,
            "page_size": request.page_size,
            "has_more": has_more,
        }
    except Exception as exc:
        write_audit_event(
            "session.list.error",
            {"company_id": company_id, "assistant_key": assistant_key, "error": str(exc)[:300]},
        )
        raise HTTPException(status_code=503, detail=f"读取会话列表失败：{exc}") from exc


@router.post("/sessions/messages")
def session_messages(
    request: SessionMessagesRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """Return one owned session's messages using a cursor for pagination."""
    if not session_repository.enabled:
        raise HTTPException(status_code=503, detail="长期会话未启用，请配置 AI_ERP_SESSION_STORE=mysql")
    request, _, company_id, user_id = api_module._persistent_identity(
        request, authorization, uid
    )
    assistant_key = request.assistant_key.strip() or get_settings().assistant_key
    try:
        items, has_more = session_repository.list_messages(
            company_id=company_id,
            assistant_key=assistant_key,
            user_id=user_id,
            session_key=request.session_id,
            before_seq=request.before_seq,
            page_size=request.page_size,
        )
        return {
            "items": items,
            "count": len(items),
            "session_id": request.session_id,
            "has_more": has_more,
            "next_before_seq": items[0]["message_seq"] if has_more and items else None,
        }
    except Exception as exc:
        write_audit_event(
            "session.messages.error",
            {
                "company_id": company_id,
                "assistant_key": assistant_key,
                "session_id": request.session_id,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(status_code=503, detail=f"读取会话消息失败：{exc}") from exc

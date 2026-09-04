"""长期会话读取接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from ai_erp_rag_assistant.app import api as api_module
from ai_erp_rag_assistant.app.assistant_catalog import APPROVAL_ASSISTANT_KEY
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
    """返回按已验证 ERP 用户和公司隔离的会话列表。"""
    request, _, company_id, user_id = api_module._persistent_identity(
        request, authorization, uid
    )
    assistant_key = request.assistant_key.strip() or api_module.get_settings().assistant_key
    # 审批助手的系统 Assistant 行由 DBA 按 docs/database/006_approval_assistant_seed.sql 配置。
    # 未配置时保留空列表，聊天接口仍可用内存模式完成当前审批。
    if assistant_key == APPROVAL_ASSISTANT_KEY:
        persistence_status = "disabled"
        if api_module.session_repository.enabled:
            try:
                configured = api_module.session_repository.assistant_available(
                    company_id=company_id,
                    assistant_key=assistant_key,
                )
                persistence_status = "ready" if configured else "not_configured"
            except Exception as exc:
                persistence_status = "unavailable"
                write_audit_event(
                    "session.list.approval_unavailable",
                    {"company_id": company_id, "assistant_key": assistant_key, "error": str(exc)[:300]},
                )
        if persistence_status != "ready":
            return {
                "items": [],
                "count": 0,
                "page": request.page,
                "page_size": request.page_size,
                "has_more": False,
                "persistence_status": persistence_status,
            }
    # 会话接口没有内存降级，避免前端误以为临时状态是长期数据。
    if not api_module.session_repository.enabled:
        raise HTTPException(status_code=503, detail="长期会话未启用，请配置 AI_ERP_SESSION_STORE=mysql")
    try:
        # Repository 查询同时包含 company_id、assistant_key 和 ERP 用户 ID。
        items, has_more = api_module.session_repository.list_sessions(
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
        api_module.write_audit_event(
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
    """使用游标分页返回当前用户拥有的一个会话消息。"""
    request, _, company_id, user_id = api_module._persistent_identity(
        request, authorization, uid
    )
    assistant_key = request.assistant_key.strip() or api_module.get_settings().assistant_key
    if assistant_key == APPROVAL_ASSISTANT_KEY:
        persistence_status = "disabled"
        if api_module.session_repository.enabled:
            try:
                configured = api_module.session_repository.assistant_available(
                    company_id=company_id,
                    assistant_key=assistant_key,
                )
                persistence_status = "ready" if configured else "not_configured"
            except Exception as exc:
                persistence_status = "unavailable"
                write_audit_event(
                    "session.messages.approval_unavailable",
                    {
                        "company_id": company_id,
                        "assistant_key": assistant_key,
                        "session_id": request.session_id,
                        "error": str(exc)[:300],
                    },
                )
        if persistence_status != "ready":
            return {
                "items": [],
                "count": 0,
                "session_id": request.session_id,
                "has_more": False,
                "next_before_seq": None,
                "persistence_status": persistence_status,
            }
    # 与列表接口保持相同的持久化开关和身份边界。
    if not api_module.session_repository.enabled:
        raise HTTPException(status_code=503, detail="长期会话未启用，请配置 AI_ERP_SESSION_STORE=mysql")
    try:
        # before_seq 使用稳定消息序号向历史翻页，不受新消息插入影响。
        items, has_more = api_module.session_repository.list_messages(
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
        api_module.write_audit_event(
            "session.messages.error",
            {
                "company_id": company_id,
                "assistant_key": assistant_key,
                "session_id": request.session_id,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(status_code=503, detail=f"读取会话消息失败：{exc}") from exc

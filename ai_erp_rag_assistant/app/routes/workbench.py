"""个人工作台只读聚合接口。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Header, HTTPException

from ai_erp_rag_assistant.app import api as api_module
from ai_erp_rag_assistant.app.schemas import WorkbenchSummaryRequest, WorkbenchSummaryResponse
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event
from ai_erp_rag_assistant.app.tools.erp_tools import get_workbench_summary


router = APIRouter(tags=["ERP Workbench"])


@router.post("/workbench/summary", response_model=WorkbenchSummaryResponse)
def workbench_summary(
    request: WorkbenchSummaryRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> WorkbenchSummaryResponse:
    """并行读取当前用户的布局、待办、审批、消息和今日考勤。"""
    request = api_module._with_header_identity(request, authorization, uid)
    try:
        user = api_module._erp_user(request)
        data = get_workbench_summary(
            user=user,
            modules={item.strip().lower() for item in request.modules if item.strip()},
            page_size=request.page_size,
            include_todo_items=request.include_todo_items,
            include_extended_todo_items=request.include_extended_todo_items,
            include_message_items=request.include_message_items,
            include_cards=request.include_cards,
        )
        data["generated_at"] = datetime.now(timezone.utc).isoformat()
        data["erp_mode"] = user.get("erp_mode", "")
        data["erp_write_mode"] = user.get("erp_write_mode", "")
        return WorkbenchSummaryResponse.model_validate(data)
    except Exception as exc:
        write_audit_event(
            "workbench.summary.error",
            {"user_id": request.user_id, "company_id": request.company_id, "error": str(exc)[:300]},
        )
        raise HTTPException(status_code=502, detail="读取 ERP 工作台失败") from exc

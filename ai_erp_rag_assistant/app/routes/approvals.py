"""ERP 审批发现和动态表单接口。"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException

from ai_erp_rag_assistant.app import api as api_module
from ai_erp_rag_assistant.app.schemas import (
    ApprovalFieldOptionsRequest,
    ApprovalFormSchemaRequest,
    ApprovalTemplatesRequest,
)
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event


router = APIRouter(tags=["ERP Approvals"])


@router.post("/approval/templates")
def approval_templates(
    request: ApprovalTemplatesRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """返回当前 ERP 用户可用的审批模板列表。"""
    request = api_module._with_header_identity(request, authorization, uid)
    try:
        user = api_module._erp_user(request)
        items = api_module.list_approval_templates(
            request.query,
            str(user.get("company_id") or request.company_id),
            user=user,
        )
        return {
            "items": items,
            "count": len(items),
            "erp_mode": user.get("erp_mode"),
            "erp_write_mode": user.get("erp_write_mode"),
        }
    except Exception as exc:
        write_audit_event(
            "approval.templates.error",
            {"user_id": request.user_id, "error": str(exc)[:300]},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/approval/form-schema")
def approval_form_schema(
    request: ApprovalFormSchemaRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """将指定 ERP 审批模板转换为前端动态表单结构。"""
    request = api_module._with_header_identity(request, authorization, uid)
    try:
        user = api_module._erp_user(request)
        template = api_module.get_approval_template(
            request.template_id,
            str(user.get("company_id") or request.company_id),
            title=request.title,
            user=user,
        )
        return api_module.build_form_schema(template, request.values)
    except Exception as exc:
        write_audit_event(
            "approval.form_schema.error",
            {
                "template_id": request.template_id,
                "user_id": request.user_id,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/approval/options")
def approval_field_options(
    request: ApprovalFieldOptionsRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """分页返回一个动态审批字段的真实 ERP 候选项。"""
    # HTTP 头中的身份信息优先，避免前端 JSON 中的旧凭据覆盖当前登录态。
    request = api_module._with_header_identity(request, authorization, uid)
    try:
        # 字段选项依赖真实公司与用户，人员、假期和关联数据不能跨租户查询。
        user = api_module._erp_user(request)
        return api_module.get_approval_field_options(
            request.template_id,
            request.field_key,
            str(user.get("company_id") or request.company_id),
            title=request.title,
            keyword=request.keyword,
            page=request.page,
            page_size=request.page_size,
            user=user,
        )
    except Exception as exc:
        write_audit_event(
            "approval.options.error",
            {
                "template_id": request.template_id,
                "field_key": request.field_key,
                "user_id": request.user_id,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

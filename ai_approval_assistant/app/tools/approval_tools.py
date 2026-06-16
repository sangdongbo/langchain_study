from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.schemas.approval import UserContext
from app.services.crm_service import crm_approval_service


class ToolUserInput(BaseModel):
    user_id: str = Field(description="业务用户 ID。")
    uid: str | None = Field(default=None, description="ERP UID。")
    authorization: str | None = Field(default=None, description="ERP Authorization。")


class SearchApprovalTemplatesInput(ToolUserInput):
    keyword: str = Field(default="", description="审批模板关键词，例如 测试外出。")


class GetApprovalFormFieldsInput(ToolUserInput):
    approval_type: str = Field(description="审批类型，例如 remote_5911。")


class GetRelatedBusinessOptionsInput(ToolUserInput):
    relate_type: str = Field(default="crmOrder", description="关联业务类型。")
    keyword: str = Field(default="", description="关联业务搜索关键词。")
    page: int = Field(default=1, ge=1, description="页码。")
    page_size: int = Field(default=20, ge=1, le=100, description="每页数量。")


@tool(args_schema=SearchApprovalTemplatesInput)
def search_approval_templates(
    user_id: str,
    keyword: str = "",
    uid: str | None = None,
    authorization: str | None = None,
) -> list[dict[str, Any]]:
    """按关键词查询当前用户可发起的审批模板。"""
    user = _tool_user(user_id, uid, authorization)
    templates = crm_approval_service.search_available_templates(user, keyword)
    return [
        {
            "approval_type": template.approval_type,
            "template_id": template.template_id,
            "title": template.title,
            "category": template.category,
            "is_common": template.is_common,
        }
        for template in templates
    ]


@tool(args_schema=GetApprovalFormFieldsInput)
def get_approval_form_fields(
    user_id: str,
    approval_type: str,
    uid: str | None = None,
    authorization: str | None = None,
) -> dict[str, Any]:
    """查询审批模板字段定义，包含必填字段、控件类型和选项。"""
    user = _tool_user(user_id, uid, authorization)
    template = crm_approval_service.get_template_detail(approval_type, user)
    return {
        "approval_type": template.approval_type,
        "template_id": template.template_id,
        "title": template.title,
        "fields": [
            {
                "name": field.name,
                "label": field.label,
                "type": field.type,
                "input_type": field.input_type,
                "required": field.required,
                "options": field.option_values or field.options,
                "group_key": field.group_key,
                "group_label": field.group_label,
                "group_type": field.group_type,
                "question": field.question,
            }
            for field in template.fields
        ],
    }


@tool(args_schema=ToolUserInput)
def get_holiday_rule_options(
    user_id: str,
    uid: str | None = None,
    authorization: str | None = None,
) -> list[dict[str, Any]]:
    """获取请假类型等假期规则选项。"""
    user = _tool_user(user_id, uid, authorization)
    return crm_approval_service.get_holiday_rules(user)


@tool(args_schema=GetRelatedBusinessOptionsInput)
def get_related_business_options(
    user_id: str,
    relate_type: str = "crmOrder",
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
    uid: str | None = None,
    authorization: str | None = None,
) -> list[dict[str, Any]]:
    """获取关联订单、关联审批等业务对象选项。"""
    user = _tool_user(user_id, uid, authorization)
    return crm_approval_service.get_related_list(
        user=user,
        relate_type=relate_type,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )


APPROVAL_TOOLS = [
    search_approval_templates,
    get_approval_form_fields,
    get_holiday_rule_options,
    get_related_business_options,
]


def _tool_user(
    user_id: str, uid: str | None = None, authorization: str | None = None
) -> UserContext:
    return crm_approval_service.get_user_context(
        user_id=user_id,
        uid=uid,
        authorization=authorization,
    )

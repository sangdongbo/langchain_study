"""供 LangGraph 节点调用的 ERP 适配器函数。"""

from __future__ import annotations

from typing import Any

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.services.erp_client import erp_client


def get_current_user(
    user_id: str,
    *,
    uid: str = "",
    authorization: str = "",
    company_id: str = "",
    department: str = "",
) -> dict[str, Any]:
    """通过 ERP 适配器读取并验证当前用户身份。"""
    return erp_client.get_current_user(
        user_id,
        uid=uid,
        authorization=authorization,
        company_id=company_id,
        department=department,
    )


def list_approval_templates(
    query: str,
    company_id: str,
    *,
    user: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """查询当前用户可发起的审批模板。"""
    return erp_client.list_approval_templates(query, company_id=company_id, user=user or {})


def get_approval_template(
    template_id: str,
    company_id: str,
    *,
    title: str = "",
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """读取指定审批模板的真实字段定义。"""
    return erp_client.get_approval_template(template_id, company_id=company_id, title=title, user=user or {})


def get_leave_template(company_id: str, *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    """供旧版示例调用方使用的向后兼容快捷入口。"""
    candidates = list_approval_templates("请假", company_id, user=user)
    if not candidates:
        raise RuntimeError("ERP 未找到请假审批模板")
    first = candidates[0]
    return get_approval_template(str(first["template_id"]), company_id, title=str(first.get("title") or ""), user=user)


def query_approval_status(user_id: str, *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    """查询当前用户的审批状态摘要。"""
    return erp_client.query_approval_status(user_id, user=user or {})


def get_approval_nodes(
    template_id: str,
    fields: dict[str, Any],
    *,
    user: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """读取指定模板和表单值对应的实时审批节点。"""
    return erp_client.get_approval_nodes(template_id, fields, user=user or {})


def get_approval_field_options(
    template_id: str,
    field_key: str,
    company_id: str,
    *,
    title: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """查询动态审批字段的远程或静态候选项。"""
    return erp_client.get_field_options(
        template_id,
        field_key,
        company_id=company_id,
        title=title,
        keyword=keyword,
        page=page,
        page_size=page_size,
        user=user or {},
    )


def get_workbench_summary(
    *,
    user: dict[str, Any],
    modules: set[str] | None = None,
    page_size: int = 5,
    include_todo_items: bool = False,
    include_extended_todo_items: bool = False,
    include_message_items: bool = True,
    include_cards: bool = False,
) -> dict[str, Any]:
    """读取个人工作台的 ERP 只读聚合数据。"""
    return erp_client.get_workbench_summary(
        user=user,
        modules=modules or set(),
        page_size=page_size,
        include_todo_items=include_todo_items,
        include_extended_todo_items=include_extended_todo_items,
        include_message_items=include_message_items,
        include_cards=include_cards,
    )


def submit_approval(preview: dict[str, Any], *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    """将已经确认的审批预览提交给 ERP 适配器。"""
    return erp_client.submit_approval(preview, user=user or {})

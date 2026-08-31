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
    return erp_client.list_approval_templates(query, company_id=company_id, user=user or {})


def get_approval_template(
    template_id: str,
    company_id: str,
    *,
    title: str = "",
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return erp_client.get_approval_template(template_id, company_id=company_id, title=title, user=user or {})


def get_leave_template(company_id: str, *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    """Backward-compatible shortcut used by older demo callers."""
    candidates = list_approval_templates("请假", company_id, user=user)
    if not candidates:
        raise RuntimeError("ERP 未找到请假审批模板")
    first = candidates[0]
    return get_approval_template(str(first["template_id"]), company_id, title=str(first.get("title") or ""), user=user)


def query_approval_status(user_id: str, *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    return erp_client.query_approval_status(user_id, user=user or {})


def get_approval_nodes(
    template_id: str,
    fields: dict[str, Any],
    *,
    user: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
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


def submit_approval(preview: dict[str, Any], *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    return erp_client.submit_approval(preview, user=user or {})

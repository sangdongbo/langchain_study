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


def get_approval_template(
    approval_type: str,
    company_id: str,
    *,
    user: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return erp_client.get_approval_template(approval_type, company_id=company_id, user=user or {})


def get_leave_template(company_id: str, *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    """Backward-compatible shortcut used by older demo callers."""
    return get_approval_template("请假", company_id, user=user)


def query_approval_status(user_id: str, *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    return erp_client.query_approval_status(user_id, user=user or {})


def submit_approval(preview: dict[str, Any], *, user: dict[str, Any] | None = None) -> dict[str, Any]:
    return erp_client.submit_approval(preview, user=user or {})

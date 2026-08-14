from __future__ import annotations

from typing import Any, TypedDict


class ErpRagState(TypedDict, total=False):
    session_id: str
    user_id: str
    user_message: str
    uid: str
    authorization: str
    company_id: str
    department: str
    confirm: bool | None
    route: str
    plan: dict[str, Any]
    user_context: dict[str, Any]
    template: dict[str, Any]
    fields: dict[str, Any]
    evidence: list[dict[str, Any]]
    erp_data: dict[str, Any]
    preview: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    errors: list[str]
    pending_question: str
    assistant_message: str


def initial_state(
    session_id: str,
    user_id: str,
    message: str,
    *,
    uid: str = "",
    authorization: str = "",
    company_id: str = "",
    department: str = "",
    confirm: bool | None = None,
    prior: ErpRagState | None = None,
) -> ErpRagState:
    prior = prior or {}
    return {
        "session_id": session_id,
        "user_id": user_id,
        "user_message": message,
        "uid": uid or prior.get("uid", ""),
        "authorization": authorization or prior.get("authorization", ""),
        "company_id": company_id or prior.get("company_id", ""),
        "department": department or prior.get("department", ""),
        "confirm": confirm,
        "route": "unknown",
        "plan": {},
        "fields": dict(prior.get("fields", {})),
        "evidence": [],
        "erp_data": {},
        "preview": dict(prior.get("preview", {})),
        "tool_calls": [],
        "errors": [],
        "pending_question": "",
        "assistant_message": "",
    }

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
    template_candidates: list[dict[str, Any]]
    conversation: list[dict[str, str]]
    fields: dict[str, Any]
    evidence: list[dict[str, Any]]
    erp_data: dict[str, Any]
    preview: dict[str, Any]
    active_approval: bool
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
    prior_active_approval = bool(prior.get("active_approval", False))
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
        "plan": dict(prior.get("plan", {})),
        "user_context": {},
        "template": dict(prior.get("template", {})),
        "template_candidates": list(prior.get("template_candidates", [])),
        "conversation": [
            *list(prior.get("conversation", [])),
            *([{"role": "assistant", "content": str(prior["pending_question"])}] if prior.get("pending_question") else []),
            {"role": "user", "content": message},
        ][-16:],
        "fields": dict(prior.get("fields", {})),
        "evidence": [],
        "erp_data": {},
        # A closed preview may be returned once for display, but it must not
        # become an actionable draft again on the next turn.
        "preview": dict(prior.get("preview", {})) if prior_active_approval else {},
        "active_approval": prior_active_approval,
        "tool_calls": [],
        "errors": [],
        "pending_question": str(prior.get("pending_question", "")),
        "assistant_message": "",
    }

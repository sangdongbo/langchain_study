from __future__ import annotations

from typing import Any, TypedDict


class ApprovalState(TypedDict, total=False):
    session_id: str
    user_id: str
    user_message: str
    status: str
    intent: str | None
    approval_type: str | None
    collected_slots: dict[str, str]
    awaiting_field: str | None
    preview: dict[str, Any] | None
    confirmed: bool
    request_id: str | None
    approval_node: str | None
    assistant_message: str
    errors: list[str]
    field_errors: list[dict[str, Any]]
    idempotency_key: str | None
    trace: list[str]
    review_count: int
    _route: str
    _user_context: dict[str, Any] | None
    _available_templates: list[dict[str, Any]]
    _validation_warnings: list[str]


def initial_state(session_id: str, user_id: str) -> ApprovalState:
    return {
        "session_id": session_id,
        "user_id": user_id,
        "user_message": "",
        "status": "idle",
        "intent": None,
        "approval_type": None,
        "collected_slots": {},
        "awaiting_field": None,
        "preview": None,
        "confirmed": False,
        "request_id": None,
        "approval_node": None,
        "assistant_message": "",
        "errors": [],
        "field_errors": [],
        "idempotency_key": None,
        "trace": [],
        "review_count": 0,
        "_route": "end",
        "_user_context": None,
        "_available_templates": [],
        "_validation_warnings": [],
    }

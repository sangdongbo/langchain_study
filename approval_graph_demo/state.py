from __future__ import annotations

from typing import Any, Literal, TypedDict


ApprovalType = Literal["leave", "expense", "purchase"]
ApprovalStatus = Literal["idle", "collecting", "awaiting_confirmation", "submitted", "cancelled"]


class ApprovalState(TypedDict, total=False):
    """State shared by the approval graph."""

    user_message: str
    approval_type: ApprovalType | None
    status: ApprovalStatus
    awaiting: str | None
    slots: dict[str, str]
    assistant_message: str
    preview: str
    confirmed: bool
    request_id: str | None
    approval_node: str | None
    errors: list[str]
    route: str
    tool_result: dict[str, Any] | None


def initial_state() -> ApprovalState:
    """Return a clean approval flow state."""

    return {
        "user_message": "",
        "approval_type": None,
        "status": "idle",
        "awaiting": None,
        "slots": {},
        "assistant_message": "",
        "preview": "",
        "confirmed": False,
        "request_id": None,
        "approval_node": None,
        "errors": [],
        "route": "classify",
        "tool_result": None,
    }


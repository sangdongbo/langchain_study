from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

from ai_deep_agents_assistant.app.schemas.approval import ApprovalPreview


ApprovalStatus = Literal[
    "idle",
    "collecting",
    "awaiting_confirmation",
    "submitted",
    "cancelled",
    "error",
]

ChatIntent = Literal["approval", "daily_report", "general"]


class ChatRequest(BaseModel):
    """Single chat turn request."""

    session_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    uid: str | None = None
    authorization: str | None = None


class ChatResponse(BaseModel):
    """Single chat turn response."""

    session_id: str
    status: ApprovalStatus
    assistant_message: str
    intent: ChatIntent = "general"
    daily_report_mode: str | None = None
    daily_report_payload: dict[str, Any] | None = None
    daily_report_preview: dict[str, Any] | None = None
    approval_type: str | None = None
    collected_slots: dict[str, str] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    awaiting_field: str | None = None
    preview: ApprovalPreview | None = None
    request_id: str | None = None
    approval_node: str | None = None
    trace: list[str] = Field(default_factory=list)
    interrupt: dict[str, Any] | None = None

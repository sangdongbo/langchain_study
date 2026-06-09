from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from ai_approval_assistant.app.schemas.approval import FieldError


ApprovalStatus = Literal["idle", "collecting", "awaiting_confirmation", "submitted", "cancelled", "error"]


class ChatRequest(BaseModel):
    session_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1)


class PreviewField(BaseModel):
    name: str
    label: str
    value: str


class ApprovalPreview(BaseModel):
    approval_type: str
    title: str
    fields: list[PreviewField]
    approval_node: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    session_id: str
    status: ApprovalStatus
    assistant_message: str
    approval_type: str | None = None
    collected_slots: dict[str, str] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    awaiting_field: str | None = None
    preview: ApprovalPreview | None = None
    actions: list[str] = Field(default_factory=list)
    request_id: str | None = None
    approval_node: str | None = None
    field_errors: list[FieldError] = Field(default_factory=list)
    idempotency_key: str | None = None
    trace: list[str] = Field(default_factory=list)

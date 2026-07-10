from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


FieldType = Literal["text", "number", "date", "enum"]


class UserContext(BaseModel):
    """User context used by the mock approval backend."""

    user_id: str
    name: str
    company_id: str
    dept_id: str
    role: str
    manager_id: str


class ApprovalField(BaseModel):
    """Single approval form field."""

    name: str
    label: str
    type: FieldType
    required: bool = True
    options: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    extract_patterns: list[str] = Field(default_factory=list)
    question: str


class ApprovalTemplate(BaseModel):
    """Approval template metadata and fields."""

    template_id: str
    approval_type: str
    title: str
    category: str
    aliases: list[str] = Field(default_factory=list)
    intent_keywords: list[str] = Field(default_factory=list)
    fields: list[ApprovalField]


class PreviewField(BaseModel):
    """Field shown in the submit preview."""

    name: str
    label: str
    value: str


class ApprovalPreview(BaseModel):
    """Human-readable approval preview before submission."""

    approval_type: str
    title: str
    fields: list[PreviewField]
    approval_node: str
    warnings: list[str] = Field(default_factory=list)


class SubmitResult(BaseModel):
    """Mock approval submit result."""

    request_id: str
    status: str
    approval_node: str
    idempotency_key: str


class ApprovalDraft(BaseModel):
    """Internal deterministic draft used by tools."""

    approval_type: str | None = None
    collected_slots: dict[str, str] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    next_question: str | None = None
    preview: ApprovalPreview | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


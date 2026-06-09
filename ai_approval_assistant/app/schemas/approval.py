from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


FieldType = Literal["text", "number", "date", "enum"]


class UserContext(BaseModel):
    user_id: str
    name: str
    company_id: str
    dept_id: str
    role: str
    manager_id: str


class ApprovalField(BaseModel):
    name: str
    label: str
    type: FieldType
    required: bool = True
    options: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    extract_patterns: list[str] = Field(default_factory=list)
    question: str


class ApprovalTemplate(BaseModel):
    template_id: str | None = None
    approval_type: str
    title: str
    category: str
    group_name: str | None = None
    aliases: list[str] = Field(default_factory=list)
    intent_keywords: list[str] = Field(default_factory=list)
    visibility: str = "all"
    enabled: bool = True
    is_common: bool = False
    sort_order: int = 100
    fields: list[ApprovalField]


class FieldError(BaseModel):
    field: str | None = None
    message: str


class ValidationResult(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    field_errors: list[FieldError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approval_node: str | None = None


class SubmitResult(BaseModel):
    request_id: str
    status: str
    approval_node: str
    idempotency_key: str | None = None

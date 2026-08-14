from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


FieldType = Literal["text", "number", "date", "enum"]


class UserContext(BaseModel):
    """模拟审批后端使用的用户上下文。"""

    user_id: str
    name: str
    company_id: str
    dept_id: str
    role: str
    manager_id: str


class ApprovalField(BaseModel):
    """单个审批表单字段。"""

    name: str
    label: str
    type: FieldType
    required: bool = True
    options: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    extract_patterns: list[str] = Field(default_factory=list)
    question: str


class ApprovalTemplate(BaseModel):
    """审批模板元数据及字段。"""

    template_id: str
    approval_type: str
    title: str
    category: str
    aliases: list[str] = Field(default_factory=list)
    intent_keywords: list[str] = Field(default_factory=list)
    fields: list[ApprovalField]


class PreviewField(BaseModel):
    """提交预览中展示的字段。"""

    name: str
    label: str
    value: str


class ApprovalPreview(BaseModel):
    """提交前供人工阅读的审批预览。"""

    approval_type: str
    title: str
    fields: list[PreviewField]
    approval_node: str
    warnings: list[str] = Field(default_factory=list)


class SubmitResult(BaseModel):
    """模拟审批提交结果。"""

    request_id: str
    status: str
    approval_node: str
    idempotency_key: str


class ApprovalDraft(BaseModel):
    """工具使用的内部确定性草稿。"""

    approval_type: str | None = None
    collected_slots: dict[str, str] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    next_question: str | None = None
    preview: ApprovalPreview | None = None
    warnings: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

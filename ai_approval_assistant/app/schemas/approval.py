from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field

FieldType = Literal["text", "number", "date", "enum"]


class UserContext(BaseModel):
    """调用 CRM/ERP 接口时使用的用户上下文。"""

    user_id: str
    name: str
    company_id: str
    dept_id: str
    role: str
    manager_id: str
    uid: str | None = None
    authorization: str | None = None


class ApprovalField(BaseModel):
    """聊天过程中需要收集的单个审批表单字段。"""

    name: str
    label: str
    type: FieldType
    required: bool = True
    options: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    extract_patterns: list[str] = Field(default_factory=list)
    question: str


class ApprovalTemplate(BaseModel):
    """当前用户可用的审批模板元数据和字段。"""

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
    """返回给聊天调用方的字段级校验错误。"""

    field: str | None = None
    message: str


class ValidationResult(BaseModel):
    """生成预览前对已收集审批字段的校验结果。"""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    field_errors: list[FieldError] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    approval_node: str | None = None


class SubmitResult(BaseModel):
    """审批申请提交后的返回结果。"""

    request_id: str
    status: str
    approval_node: str
    idempotency_key: str | None = None

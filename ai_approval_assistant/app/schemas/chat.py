from __future__ import annotations
from typing import Any, Literal
from pydantic import BaseModel, Field
from app.schemas.approval import FieldError

ApprovalStatus = Literal[
    "idle",
    "collecting",
    "awaiting_assignee_selection",
    "awaiting_confirmation",
    "submitted",
    "cancelled",
    "error",
    "awaiting_daily_report_form",
    "awaiting_daily_report_confirmation",
    "daily_report_submitted",
]


class ChatRequest(BaseModel):
    """单轮聊天请求体。"""

    session_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    message: str = Field(min_length=1)
    uid: str | None = None
    authorization: str | None = None
    answer: dict[str, Any] | None = None


class AwaitingInput(BaseModel):
    """前端可直接渲染的当前等待输入控件描述。"""

    field_key: str
    label: str
    type: Literal[
        "single_select",
        "user_select",
        "datetime",
        "date",
        "text",
        "textarea",
        "address",
    ]
    required: bool = True
    placeholder: str = ""
    options: list[dict[str, Any]] = Field(default_factory=list)
    multiple: bool | None = None
    min: Any | None = None
    max: Any | None = None
    value_schema: dict[str, str] | None = None
    value: Any | None = None


class PreviewField(BaseModel):
    """审批预览中展示的字段和值。"""

    name: str
    label: str
    value: str


class ApprovalPreview(BaseModel):
    """提交前生成的可读审批预览。"""

    approval_type: str
    title: str
    fields: list[PreviewField]
    approval_node: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ChatResponse(BaseModel):
    """单轮聊天处理后的响应体。"""

    session_id: str
    status: ApprovalStatus
    assistant_message: str
    approval_type: str | None = None
    collected_slots: dict[str, str] = Field(default_factory=dict)
    collected_values: dict[str, Any] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    missing_field_keys: list[str] = Field(default_factory=list)
    missing_field_labels: list[str] = Field(default_factory=list)
    awaiting_field: str | None = None
    awaiting_field_key: str | None = None
    awaiting_field_label: str | None = None
    awaiting_input: AwaitingInput | None = None
    preview: ApprovalPreview | None = None
    actions: list[str] = Field(default_factory=list)
    request_id: str | None = None
    approval_node: str | None = None
    field_errors: list[FieldError] = Field(default_factory=list)
    idempotency_key: str | None = None
    trace: list[str] = Field(default_factory=list)
    ui_action: dict[str, Any] | None = None
    daily_report_payload: dict[str, Any] | None = None
    daily_report_preview: dict[str, Any] | None = None

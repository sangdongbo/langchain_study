from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1)
    session_id: str = Field(default="demo-session", min_length=1, max_length=128)
    request_id: str = Field(default="", max_length=64)
    assistant_key: str = Field(default="", max_length=64)
    user_id: str = Field(default="U001", min_length=1, max_length=64)
    uid: str = ""
    authorization: str = ""
    company_id: str = ""
    department: str = ""
    confirm: bool | None = None
    preview_id: str = ""
    preview_version: int | None = None
    preview_hash: str = ""
    form_values: dict[str, Any] = Field(default_factory=dict)
    selected_assignees: dict[str, list[str]] = Field(default_factory=dict)
    reset: bool = False


class ChatResponse(BaseModel):
    message: str
    route: Literal["knowledge", "erp_status", "approval_workflow", "general_chat", "unknown"]
    plan: dict[str, Any] = Field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[str] = Field(default_factory=list)
    pending_question: str = ""
    workflow_status: str = "idle"
    erp_mode: str = ""
    erp_write_mode: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    erp_data: dict[str, Any] = Field(default_factory=dict)
    form_schema: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None


class ApprovalApiContext(BaseModel):
    user_id: str = Field(min_length=1, max_length=64)
    assistant_key: str = Field(default="", max_length=64)
    uid: str = ""
    authorization: str = ""
    company_id: str = ""
    department: str = ""


class ApprovalTemplatesRequest(ApprovalApiContext):
    query: str = ""


class ApprovalFormSchemaRequest(ApprovalApiContext):
    template_id: str
    title: str = ""
    values: dict[str, Any] = Field(default_factory=dict)


class ApprovalFieldOptionsRequest(ApprovalApiContext):
    template_id: str
    field_key: str
    title: str = ""
    keyword: str = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


class SessionListRequest(ApprovalApiContext):
    """前端按当前 ERP 用户分页读取长期会话。"""

    status: Literal["active", "archived"] = "active"
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class SessionMessagesRequest(ApprovalApiContext):
    """前端读取单个会话的消息；before_seq 是向前翻页游标。"""

    session_id: str = Field(min_length=1, max_length=128)
    # 使用消息序号而非页码，避免新消息写入后产生重复或漏读。
    before_seq: int | None = Field(default=None, ge=1)
    page_size: int = Field(default=50, ge=1, le=200)


class RagSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=10000)
    user_id: str = Field(default="", max_length=64)
    uid: str = Field(default="", max_length=64)
    authorization: str = ""
    company_id: str = Field(min_length=1, max_length=64)
    assistant_key: str = Field(default="", max_length=64)
    knowledge_base_key: str = Field(default="", max_length=64)
    department: str = Field(default="", max_length=256)
    permission_tags: list[str] = Field(default_factory=list, max_length=32)
    top_k: int | None = Field(default=None, ge=1, le=50)


class RagChatRequest(RagSearchRequest):
    system_context: str = Field(default="", max_length=4000)


class RagEvidenceResponse(BaseModel):
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    company_id: str
    knowledge_base_key: str = ""
    collection: str


class RagChatResponse(BaseModel):
    message: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    company_id: str
    knowledge_base_key: str = ""
    collection: str


class RagTextIngestRequest(BaseModel):
    content: str = Field(min_length=1, max_length=2_000_000)
    user_id: str = Field(default="", max_length=64)
    uid: str = Field(default="", max_length=64)
    authorization: str = ""
    company_id: str = Field(min_length=1, max_length=64)
    source: str = Field(min_length=1, max_length=1000)
    title: str = Field(default="", max_length=1000)
    knowledge_base_key: str = Field(default="", max_length=64)
    department: str = Field(default="", max_length=256)
    version: str = Field(default="", max_length=128)
    effective_date: str = Field(default="", max_length=128)
    permission_tags: list[str] = Field(default_factory=list, max_length=32)
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)


class RagIngestResponse(BaseModel):
    status: Literal["completed"] = "completed"
    source: str
    chunk_count: int
    inserted_count: int
    empty_pages: list[int] = Field(default_factory=list)
    company_id: str
    knowledge_base_key: str = ""
    collection: str

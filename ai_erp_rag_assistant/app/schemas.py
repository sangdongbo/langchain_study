"""聊天、审批、RAG 检索、导入和文档管理接口的数据契约。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    """一次聊天工作流请求，包含会话、身份和可选审批确认信息。"""

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
    """聊天工作流响应以及检索、ERP、表单和预览结果。"""

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
    citations: list["RagCitation"] = Field(default_factory=list)
    erp_data: dict[str, Any] = Field(default_factory=dict)
    form_schema: dict[str, Any] | None = None
    preview: dict[str, Any] | None = None


class ApprovalApiContext(BaseModel):
    """审批辅助接口共用的 ERP 用户与租户上下文。"""

    user_id: str = Field(min_length=1, max_length=64)
    assistant_key: str = Field(default="", max_length=64)
    uid: str = ""
    authorization: str = ""
    company_id: str = ""
    department: str = ""


class ApprovalTemplatesRequest(ApprovalApiContext):
    """按用户输入检索当前公司可用审批模板。"""

    query: str = ""


class ApprovalFormSchemaRequest(ApprovalApiContext):
    """请求指定审批模板的前端动态表单结构。"""

    template_id: str
    title: str = ""
    values: dict[str, Any] = Field(default_factory=dict)


class ApprovalFieldOptionsRequest(ApprovalApiContext):
    """分页查询一个动态审批字段的候选选项。"""

    template_id: str
    field_key: str
    title: str = ""
    keyword: str = ""
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=200)


class WorkbenchSummaryRequest(ApprovalApiContext):
    """读取个人工作台的只读聚合数据。"""

    modules: list[str] = Field(default_factory=list, max_length=16)
    page_size: int = Field(default=5, ge=1, le=20)
    include_todo_items: bool = False
    include_extended_todo_items: bool = False
    include_message_items: bool = True
    include_cards: bool = False


class WorkbenchSummaryResponse(BaseModel):
    """个人工作台稳定返回契约；单个模块失败不影响其他模块。"""

    generated_at: str
    user: dict[str, Any] = Field(default_factory=dict)
    counts: dict[str, Any] = Field(default_factory=dict)
    layout: dict[str, Any] = Field(default_factory=dict)
    todo: dict[str, Any] = Field(default_factory=dict)
    approvals: dict[str, Any] = Field(default_factory=dict)
    messages: dict[str, Any] = Field(default_factory=dict)
    attendance: dict[str, Any] = Field(default_factory=dict)
    cards: list[dict[str, Any]] = Field(default_factory=list)
    erp_mode: str = ""
    erp_write_mode: str = ""


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
    """在 ERP 验证身份下执行租户知识库检索。"""

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
    """检索知识后调用 LLM 生成答案的请求。"""

    system_context: str = Field(default="", max_length=4000)


class RagCitation(BaseModel):
    """前端可直接展示或定位原文的稳定引用信息。"""

    citation_id: int = Field(ge=1)
    chunk_id: str = ""
    source: str
    title: str = ""
    page: int | None = Field(default=None, ge=1)
    score: float | None = None
    snippet: str = ""


class RagEvidenceResponse(BaseModel):
    """不调用 LLM 的原始知识检索结果。"""

    evidence: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[RagCitation] = Field(default_factory=list)
    count: int = 0
    company_id: str
    knowledge_base_key: str = ""
    collection: str


class RagChatResponse(BaseModel):
    """LLM 答案及其知识库证据。"""

    message: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    citations: list[RagCitation] = Field(default_factory=list)
    count: int = 0
    company_id: str
    knowledge_base_key: str = ""
    collection: str


class RagTextIngestRequest(BaseModel):
    """同步切分并导入一段文本的请求。"""

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
    # 使用 None 区分“前端未传”与“前端明确覆盖”，路由才能应用知识库默认配置。
    chunk_size: int | None = Field(default=None, ge=100, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1000)


class RagIngestResponse(BaseModel):
    """同步导入完成后的 Chunk、空页和 Collection 统计。"""

    status: Literal["completed"] = "completed"
    source: str
    chunk_count: int
    inserted_count: int
    empty_pages: list[int] = Field(default_factory=list)
    company_id: str
    knowledge_base_key: str = ""
    collection: str
    job_id: int | None = None
    job_key: str = ""


class RagIngestJobRequest(BaseModel):
    """查询或重试一个当前租户的同步导入任务。"""

    user_id: str = Field(default="", max_length=64)
    uid: str = Field(default="", max_length=64)
    authorization: str = ""
    company_id: str = Field(min_length=1, max_length=64)
    knowledge_base_key: str = Field(min_length=1, max_length=64)
    department: str = Field(default="", max_length=256)
    job_id: int = Field(ge=1)


class RagIngestJobResponse(BaseModel):
    """导入阶段、计数、失败原因和是否可补偿。"""

    id: int
    job_key: str
    status: Literal["pending", "parsing", "embedding", "completed", "failed"]
    document_id: int
    document_status: str
    source: str
    knowledge_base_key: str
    total_pages: int | None = None
    parsed_pages: int = 0
    chunk_count: int = 0
    inserted_chunk_count: int = 0
    error_code: str | None = None
    error_message: str | None = None
    retryable: bool = False


class RagDocumentListRequest(BaseModel):
    """按当前用户可见范围分页查询知识库文档。"""

    user_id: str = Field(default="", max_length=64)
    uid: str = Field(default="", max_length=64)
    authorization: str = ""
    company_id: str = Field(min_length=1, max_length=64)
    knowledge_base_key: str = Field(min_length=1, max_length=64)
    department: str = Field(default="", max_length=256)
    keyword: str = Field(default="", max_length=255)
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1, le=100)


class RagDocumentDeleteRequest(BaseModel):
    """按来源和版本精确删除一个可见文档。"""

    user_id: str = Field(default="", max_length=64)
    uid: str = Field(default="", max_length=64)
    authorization: str = ""
    company_id: str = Field(min_length=1, max_length=64)
    knowledge_base_key: str = Field(min_length=1, max_length=64)
    department: str = Field(default="", max_length=256)
    source: str = Field(min_length=1, max_length=1000)
    version: str = Field(default="", max_length=128)


class RagDocumentListResponse(BaseModel):
    """由可见 Chunk 聚合得到的文档分页结果。"""

    items: list[dict[str, Any]] = Field(default_factory=list)
    count: int = 0
    total: int = 0
    page: int
    page_size: int
    company_id: str
    knowledge_base_key: str
    collection: str


class RagDocumentDeleteResponse(BaseModel):
    """文档删除结果及实际删除的 Chunk 数。"""

    status: Literal["deleted"] = "deleted"
    source: str
    version: str = ""
    deleted_chunk_count: int
    company_id: str
    knowledge_base_key: str
    collection: str

"""RAG 管理端请求模型以及敏感配置和参数组合校验。"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _reject_inline_secrets(*values: Any) -> None:
    """递归阻止密码、Token 等凭据直接写入普通 JSON 配置。"""
    forbidden = {"api_key", "authorization", "cookie", "password", "secret", "token"}

    def visit(value: Any) -> None:
        """递归检查嵌套字典和列表中的敏感键名。"""
        if isinstance(value, dict):
            for key, item in value.items():
                normalized = str(key).lower().replace("-", "_")
                if any(normalized == name or normalized.endswith(f"_{name}") for name in forbidden):
                    raise ValueError(f"{key} 不得直接写入配置，请改用密钥引用")
                visit(item)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    for value in values:
        visit(value)


def _validate_retrieval_config(value: dict[str, Any]) -> None:
    """校验当前运行时真正支持的检索与重排参数，避免发布无效配置。"""
    if "top_k" in value and (
        not isinstance(value["top_k"], int) or not 1 <= value["top_k"] <= 50
    ):
        raise ValueError("retrieval_config.top_k 必须为 1..50 的整数")
    if "score_threshold" in value and (
        not isinstance(value["score_threshold"], (int, float))
        or isinstance(value["score_threshold"], bool)
        or not -1 <= float(value["score_threshold"]) <= 1
    ):
        raise ValueError("retrieval_config.score_threshold 必须为 -1..1 的数字")
    if "rerank_enabled" in value and not isinstance(value["rerank_enabled"], bool):
        raise ValueError("retrieval_config.rerank_enabled 必须为布尔值")
    if "rerank_candidates" in value and (
        not isinstance(value["rerank_candidates"], int)
        or not 1 <= value["rerank_candidates"] <= 50
    ):
        raise ValueError("retrieval_config.rerank_candidates 必须为 1..50 的整数")


def _validate_permission_policy(value: dict[str, Any]) -> None:
    """校验服务端支持的部门和权限标签策略字段。"""
    for key in (
        "allowed_departments",
        "required_tags",
        "any_tags",
        "read_required_tags",
        "write_required_tags",
        "delete_required_tags",
    ):
        if key not in value:
            continue
        raw = value[key]
        values = [raw] if isinstance(raw, str) else raw
        if not isinstance(values, list) or any(
            not isinstance(item, str) or not item.strip() for item in values
        ):
            raise ValueError(f"{key} 必须是非空字符串或字符串数组")


class AdminContext(BaseModel):
    """所有管理请求共用的 ERP 身份和公司上下文。"""

    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(default="", max_length=64)
    uid: str = Field(default="", max_length=64)
    authorization: str = ""
    company_id: str = Field(min_length=1, max_length=64)
    department: str = Field(default="", max_length=256)


class AdminListRequest(AdminContext):
    """按启用状态筛选公司内管理对象。"""

    status: Literal["active", "disabled", "archived"] | None = None


class AdminPublishRequest(AdminContext):
    """发布版本时只需要可信身份上下文。"""

    pass


class AssistantCreateRequest(AdminContext):
    """创建公司内唯一的 Assistant 业务身份。"""

    assistant_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)


class AssistantUpdateRequest(AdminContext):
    """修改 Assistant 展示信息或状态，业务标识 assistant_key 保持不变。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    status: Literal["active", "disabled", "archived"] | None = None

    @model_validator(mode="after")
    def require_change(self) -> "AssistantUpdateRequest":
        """拒绝没有任何业务字段的空更新。"""
        if self.name is None and self.status is None:
            raise ValueError("至少需要提交一个可修改字段")
        return self


class AssistantConfigCreateRequest(AdminContext):
    """创建一个新的 Assistant 配置草稿版本。"""

    page_config: dict[str, Any] = Field(default_factory=dict)
    # model_config 是 Pydantic 保留属性，内部改名并通过 alias 保持前端 JSON 契约不变。
    model_settings: dict[str, Any] = Field(
        default_factory=dict,
        validation_alias="model_config",
        serialization_alias="model_config",
    )
    retrieval_config: dict[str, Any] = Field(default_factory=dict)
    feature_flags: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "AssistantConfigCreateRequest":
        """确保版本配置只包含可持久化的非敏感模型参数。"""
        _reject_inline_secrets(
            self.page_config, self.model_settings, self.retrieval_config, self.feature_flags
        )
        _validate_retrieval_config(self.retrieval_config)
        return self


class PromptCreateRequest(AdminContext):
    """创建指定用途和变体的 Prompt 草稿版本。"""

    prompt_key: str = Field(min_length=1, max_length=64)
    variant: Literal["primary", "secondary"] = "primary"
    content: str = Field(min_length=1, max_length=100_000)
    model_overrides: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "PromptCreateRequest":
        """禁止通过 Prompt 模型覆盖参数保存连接凭据。"""
        _reject_inline_secrets(self.model_overrides)
        return self


class PromptListRequest(AdminContext):
    """按 Prompt 用途和变体筛选版本列表。"""

    prompt_key: str = Field(default="", max_length=64)
    variant: Literal["primary", "secondary"] | None = None


class KnowledgeBaseCreateRequest(AdminContext):
    """创建知识库及其不可变的 Embedding 和 Collection 身份。"""

    knowledge_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    description: str = Field(default="", max_length=10_000)
    embedding_provider: str = Field(default="openai-compatible", min_length=1, max_length=64)
    embedding_model: str = Field(default="", max_length=128)
    embedding_dimension: int | None = Field(default=None, ge=1)
    chunk_size: int = Field(default=800, ge=100, le=4000)
    chunk_overlap: int = Field(default=120, ge=0, le=1000)
    default_top_k: int = Field(default=5, ge=1, le=50)
    default_score_threshold: float = Field(default=0.65, ge=0, le=1)
    permission_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_chunking(self) -> "KnowledgeBaseCreateRequest":
        """保证 Chunk 重叠长度严格小于单个 Chunk 长度。"""
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        _validate_permission_policy(self.permission_config)
        return self


class KnowledgeBaseUpdateRequest(AdminContext):
    """修改知识库运行参数，不允许改变 Collection 和 Embedding 身份。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = Field(default=None, max_length=10_000)
    status: Literal["active", "disabled", "archived"] | None = None
    chunk_size: int | None = Field(default=None, ge=100, le=4000)
    chunk_overlap: int | None = Field(default=None, ge=0, le=1000)
    default_top_k: int | None = Field(default=None, ge=1, le=50)
    default_score_threshold: float | None = Field(default=None, ge=0, le=1)
    permission_config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "KnowledgeBaseUpdateRequest":
        """拒绝空更新，并校验请求同时携带的切分参数。"""
        values = (
            self.name,
            self.description,
            self.status,
            self.chunk_size,
            self.chunk_overlap,
            self.default_top_k,
            self.default_score_threshold,
            self.permission_config,
        )
        if all(value is None for value in values):
            raise ValueError("至少需要提交一个可修改字段")
        if (
            self.chunk_size is not None
            and self.chunk_overlap is not None
            and self.chunk_overlap >= self.chunk_size
        ):
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        if self.permission_config is not None:
            _validate_permission_policy(self.permission_config)
        return self


class DataSourceCreateRequest(AdminContext):
    """创建仅保存非敏感连接信息的数据源。"""

    source_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    source_type: Literal["file", "database", "api"]
    config: dict[str, Any] = Field(default_factory=dict)
    credentials_ref: str = Field(default="", max_length=255)
    sync_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "DataSourceCreateRequest":
        """强制敏感信息使用 credentials_ref 外部引用。"""
        _reject_inline_secrets(self.config, self.sync_config)
        return self


class DataSourceUpdateRequest(AdminContext):
    """修改数据源的非敏感配置，source_key 和 source_type 保持不变。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: Literal["active", "disabled", "archived"] | None = None
    config: dict[str, Any] | None = None
    credentials_ref: str | None = Field(default=None, max_length=255)
    sync_config: dict[str, Any] | None = None

    @model_validator(mode="after")
    def validate_update(self) -> "DataSourceUpdateRequest":
        """拒绝空更新并再次检查修改后的配置不含凭据。"""
        if all(
            value is None
            for value in (
                self.name,
                self.status,
                self.config,
                self.credentials_ref,
                self.sync_config,
            )
        ):
            raise ValueError("至少需要提交一个可修改字段")
        _reject_inline_secrets(self.config, self.sync_config)
        return self


class AssistantKnowledgeBaseBindRequest(AdminContext):
    """创建或更新 Assistant 与知识库的检索绑定。"""

    assistant_id: int = Field(ge=1)
    knowledge_base_id: int = Field(ge=1)
    enabled: bool = True
    priority: int = 0
    retrieval_config: dict[str, Any] = Field(default_factory=dict)
    permission_filter: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_runtime_filters(self) -> "AssistantKnowledgeBaseBindRequest":
        """绑定级配置必须能被当前运行时明确解释。"""
        _validate_retrieval_config(self.retrieval_config)
        _validate_permission_policy(self.permission_filter)
        return self


class AssistantKnowledgeBaseListRequest(AdminContext):
    """按 Assistant、知识库和启用状态筛选租户内绑定关系。"""

    assistant_id: int | None = Field(default=None, ge=1)
    knowledge_base_id: int | None = Field(default=None, ge=1)
    enabled: bool | None = None


class KnowledgeBaseSourceBindRequest(AdminContext):
    """创建或更新知识库与数据源的导入绑定。"""

    knowledge_base_id: int = Field(ge=1)
    data_source_id: int = Field(ge=1)
    enabled: bool = True
    priority: int = 0
    import_config: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseSourceListRequest(AdminContext):
    """按知识库、数据源和启用状态筛选租户内绑定关系。"""

    knowledge_base_id: int | None = Field(default=None, ge=1)
    data_source_id: int | None = Field(default=None, ge=1)
    enabled: bool | None = None

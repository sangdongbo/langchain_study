from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def _reject_inline_secrets(*values: Any) -> None:
    forbidden = {"api_key", "authorization", "cookie", "password", "secret", "token"}

    def visit(value: Any) -> None:
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


class AdminContext(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(default="", max_length=64)
    uid: str = Field(default="", max_length=64)
    authorization: str = ""
    company_id: str = Field(min_length=1, max_length=64)
    department: str = Field(default="", max_length=256)


class AdminListRequest(AdminContext):
    status: Literal["active", "disabled", "archived"] | None = None


class AdminPublishRequest(AdminContext):
    pass


class AssistantCreateRequest(AdminContext):
    assistant_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=64)


class AssistantConfigCreateRequest(AdminContext):
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
        _reject_inline_secrets(
            self.page_config, self.model_settings, self.retrieval_config, self.feature_flags
        )
        return self


class PromptCreateRequest(AdminContext):
    prompt_key: str = Field(min_length=1, max_length=64)
    variant: Literal["primary", "secondary"] = "primary"
    content: str = Field(min_length=1, max_length=100_000)
    model_overrides: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "PromptCreateRequest":
        _reject_inline_secrets(self.model_overrides)
        return self


class PromptListRequest(AdminContext):
    prompt_key: str = Field(default="", max_length=64)
    variant: Literal["primary", "secondary"] | None = None


class KnowledgeBaseCreateRequest(AdminContext):
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
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        return self


class DataSourceCreateRequest(AdminContext):
    source_key: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    source_type: Literal["file", "database", "api"]
    config: dict[str, Any] = Field(default_factory=dict)
    credentials_ref: str = Field(default="", max_length=255)
    sync_config: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def reject_inline_secrets(self) -> "DataSourceCreateRequest":
        _reject_inline_secrets(self.config, self.sync_config)
        return self


class AssistantKnowledgeBaseBindRequest(AdminContext):
    assistant_id: int = Field(ge=1)
    knowledge_base_id: int = Field(ge=1)
    enabled: bool = True
    priority: int = 0
    retrieval_config: dict[str, Any] = Field(default_factory=dict)
    permission_filter: dict[str, Any] = Field(default_factory=dict)


class KnowledgeBaseSourceBindRequest(AdminContext):
    knowledge_base_id: int = Field(ge=1)
    data_source_id: int = Field(ge=1)
    enabled: bool = True
    priority: int = 0
    import_config: dict[str, Any] = Field(default_factory=dict)

"""映射人工创建的 RAG 管理、文档和同步任务表，不负责建表。"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import CHAR, JSON, Computed, Numeric, String, Text, text
from sqlalchemy.dialects.mysql import BIGINT, DATETIME, INTEGER, MEDIUMTEXT, SMALLINT, TINYINT
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """项目 SQLAlchemy ORM 模型的声明式基类。"""

    pass


class Assistant(Base):
    """公司内稳定的 Assistant 身份及当前发布配置指针。"""

    __tablename__ = "ai_erp_assistants"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assistant_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="active")
    published_config_version_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True))
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class AssistantConfigVersion(Base):
    """Assistant 的不可变版本配置及发布状态。"""

    __tablename__ = "ai_erp_assistant_config_versions"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assistant_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="draft")
    published_slot: Mapped[int | None] = mapped_column(
        TINYINT(), Computed("CASE WHEN status = 'published' THEN 1 ELSE NULL END", persisted=True)
    )
    page_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    model_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    retrieval_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    feature_flags_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    config_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    created_by: Mapped[str | None] = mapped_column(String(64))
    published_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    published_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    archived_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class PromptVersion(Base):
    """按用途和变体保存的版本化 Prompt。"""

    __tablename__ = "ai_erp_prompt_versions"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assistant_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    prompt_key: Mapped[str] = mapped_column(String(64), nullable=False)
    variant: Mapped[str] = mapped_column(String(16), nullable=False, server_default="primary")
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="draft")
    published_slot: Mapped[int | None] = mapped_column(
        TINYINT(), Computed("CASE WHEN status = 'published' THEN 1 ELSE NULL END", persisted=True)
    )
    content: Mapped[str] = mapped_column(MEDIUMTEXT, nullable=False)
    content_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    model_overrides_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(String(64))
    published_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    published_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    archived_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class BlockedTerm(Base):
    """Assistant 级敏感词或阻断词回复规则。"""

    __tablename__ = "ai_erp_blocked_terms"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assistant_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    term: Mapped[str] = mapped_column(String(255), nullable=False)
    match_type: Mapped[str] = mapped_column(String(16), nullable=False, server_default="contains")
    reply_content: Mapped[str] = mapped_column(String(255), nullable=False)
    enabled: Mapped[bool] = mapped_column(TINYINT(1), nullable=False, server_default="1")
    sort_order: Mapped[int] = mapped_column(INTEGER(), nullable=False, server_default="0")
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))


class KnowledgeBase(Base):
    """知识库检索、切分、Embedding 与 Milvus Collection 配置。"""

    __tablename__ = "ai_erp_knowledge_bases"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="active")
    milvus_collection: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_provider: Mapped[str] = mapped_column(String(64), nullable=False)
    embedding_model: Mapped[str] = mapped_column(String(128), nullable=False)
    embedding_dimension: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False)
    chunk_size: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="800")
    chunk_overlap: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="120")
    default_top_k: Mapped[int] = mapped_column(SMALLINT(unsigned=True), nullable=False, server_default="5")
    default_score_threshold: Mapped[Decimal] = mapped_column(Numeric(6, 5), nullable=False, server_default="0.65000")
    permission_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="1")
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class DataSource(Base):
    """文件、数据库或 API 来源的非敏感同步配置。"""

    __tablename__ = "ai_erp_data_sources"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    source_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="active")
    config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    credentials_ref: Mapped[str | None] = mapped_column(String(255))
    sync_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class KnowledgeBaseSource(Base):
    """知识库与数据源之间的租户内绑定关系。"""

    __tablename__ = "ai_erp_knowledge_base_sources"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    data_source_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(TINYINT(1), nullable=False, server_default="1")
    priority: Mapped[int] = mapped_column(INTEGER(), nullable=False, server_default="0")
    import_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))


class AssistantKnowledgeBase(Base):
    """Assistant 与知识库之间的检索及权限绑定配置。"""

    __tablename__ = "ai_erp_assistant_knowledge_bases"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    assistant_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    enabled: Mapped[bool] = mapped_column(TINYINT(1), nullable=False, server_default="1")
    priority: Mapped[int] = mapped_column(INTEGER(), nullable=False, server_default="0")
    retrieval_config_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    permission_filter_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))


class KnowledgeDocument(Base):
    """可追溯、可版本化的知识文档元数据。"""

    __tablename__ = "ai_erp_knowledge_documents"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    data_source_id: Mapped[int | None] = mapped_column(BIGINT(unsigned=True))
    document_key: Mapped[str] = mapped_column(String(64), nullable=False)
    source_type: Mapped[str] = mapped_column(String(24), nullable=False, server_default="upload")
    file_name: Mapped[str | None] = mapped_column(String(255))
    title: Mapped[str | None] = mapped_column(String(255))
    mime_type: Mapped[str | None] = mapped_column(String(127))
    storage_uri: Mapped[str | None] = mapped_column(String(1024))
    source_record_key: Mapped[str | None] = mapped_column(String(255))
    content_sha256: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    version: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="1")
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="uploaded")
    effective_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    expired_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    permission_scope_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    page_count: Mapped[int | None] = mapped_column(INTEGER(unsigned=True))
    character_count: Mapped[int | None] = mapped_column(BIGINT(unsigned=True))
    created_by: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    updated_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))
    deleted_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))


class KnowledgeIngestJob(Base):
    """文档解析、切分和向量写入过程的审计任务记录。"""

    __tablename__ = "ai_erp_knowledge_ingest_jobs"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    document_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    job_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    parser: Mapped[str | None] = mapped_column(String(64))
    embedding_model: Mapped[str | None] = mapped_column(String(128))
    total_pages: Mapped[int | None] = mapped_column(INTEGER(unsigned=True))
    parsed_pages: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="0")
    chunk_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="0")
    inserted_chunk_count: Mapped[int] = mapped_column(INTEGER(unsigned=True), nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))


class DataSourceSyncJob(Base):
    """数据库或 API 数据源同步过程的进度与错误记录。"""

    __tablename__ = "ai_erp_data_source_sync_jobs"

    id: Mapped[int] = mapped_column(BIGINT(unsigned=True), primary_key=True, autoincrement=True)
    company_id: Mapped[str] = mapped_column(String(64), nullable=False)
    knowledge_base_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    data_source_id: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False)
    job_key: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, server_default="pending")
    cursor_json: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    total_records: Mapped[int | None] = mapped_column(BIGINT(unsigned=True))
    processed_records: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, server_default="0")
    created_document_count: Mapped[int] = mapped_column(BIGINT(unsigned=True), nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64))
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    completed_at: Mapped[datetime | None] = mapped_column(DATETIME(fsp=6))
    created_at: Mapped[datetime] = mapped_column(DATETIME(fsp=6), nullable=False, server_default=text("CURRENT_TIMESTAMP(6)"))

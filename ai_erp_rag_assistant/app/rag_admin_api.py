"""RAG 管理 HTTP 接口，负责身份校验、错误映射和仓储调用。"""

from __future__ import annotations

from collections.abc import Callable, Generator
from typing import Annotated, Any, TypeVar

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.database import DatabaseNotConfiguredError, get_db_session
from ai_erp_rag_assistant.app.rag_admin_repository import (
    AdminNotFoundError,
    RagAdminRepository,
    row_dict,
)
from ai_erp_rag_assistant.app.rag_admin_schemas import (
    AdminContext,
    AdminListRequest,
    AdminPublishRequest,
    AssistantConfigCreateRequest,
    AssistantCreateRequest,
    AssistantKnowledgeBaseBindRequest,
    AssistantKnowledgeBaseListRequest,
    AssistantUpdateRequest,
    DataSourceCreateRequest,
    DataSourceUpdateRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseSourceBindRequest,
    KnowledgeBaseSourceListRequest,
    KnowledgeBaseUpdateRequest,
    PromptCreateRequest,
    PromptListRequest,
)
from ai_erp_rag_assistant.app.services.milvus_service import milvus_service
from ai_erp_rag_assistant.app.tools.erp_tools import get_current_user


router = APIRouter(prefix="/rag/admin", tags=["RAG Admin"])
T = TypeVar("T")


def _required_db() -> Generator[Session, None, None]:
    """为管理接口强制提供 MySQL Session，并转换未配置错误。"""
    try:
        yield from get_db_session()
    except DatabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


DbSession = Annotated[Session, Depends(_required_db)]


def _identity(
    request: AdminContext, authorization: str | None, uid: str | None
) -> tuple[str, str]:
    """通过 ERP 身份确认 company_id，并返回审计操作人。"""
    request = request.model_copy(
        update={
            # 与普通 RAG 接口保持一致：HTTP 头是当前登录态，请求体只作为兼容兜底。
            "authorization": authorization or request.authorization or "",
            "uid": uid or request.uid or "",
        }
    )
    try:
        user = get_current_user(
            request.user_id,
            uid=request.uid,
            authorization=request.authorization,
            company_id=request.company_id,
            department=request.department,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    company_id = str(user.get("company_id") or "").strip()
    # 前端可不重复提交公司 ID；若显式提交，仍必须与 ERP 已验证租户一致。
    if not company_id or (
        request.company_id.strip() and company_id != request.company_id.strip()
    ):
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    actor = str(user.get("uid") or user.get("user_id") or request.uid or request.user_id).strip()
    return company_id, actor


def _run(session: Session, operation: Callable[[], T]) -> T:
    """执行仓储操作并将常见数据库和业务异常映射为 HTTP 状态码。"""
    try:
        return operation()
    except AdminNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="业务标识或版本已存在") from exc
    except ValueError as exc:
        session.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail="MySQL 操作失败") from exc


def _list_response(rows: list[Any]) -> dict[str, Any]:
    """将 ORM 列表转换为统一的 items/count 响应结构。"""
    items = [row_dict(row) for row in rows]
    return {"items": items, "count": len(items)}


def _config_response(row: Any) -> dict[str, Any]:
    """转换配置版本响应，隐藏数据库 JSON 后缀并返回前端可直接使用的字段。"""
    item = row_dict(row)
    # 数据库列名保留 JSON 后缀以区分 ORM 原始结构，HTTP 契约使用更直观的数组名称。
    configured_keys = item.pop("knowledge_base_keys_json", None)
    item["knowledge_base_keys"] = (
        [str(key).strip() for key in configured_keys if str(key).strip()]
        if isinstance(configured_keys, (list, tuple))
        else []
    )
    return item


def _config_list_response(rows: list[Any]) -> dict[str, Any]:
    """批量转换配置版本，确保创建、查询和发布接口返回一致结构。"""
    items = [_config_response(row) for row in rows]
    return {"items": items, "count": len(items)}


def _knowledge_embedding_config(
    request: KnowledgeBaseCreateRequest,
) -> tuple[str, str, int]:
    """确保新知识库使用当前进程真正加载的 Embedding 模型与维度。"""
    settings = get_settings()
    provider = request.embedding_provider.strip().lower()
    model = request.embedding_model.strip() or settings.embedding_model
    dimension = request.embedding_dimension or settings.embedding_dimensions

    # 当前 Embedding 与 Milvus 服务都是单例，只能使用进程级模型和向量维度。
    if (
        provider != "openai-compatible"
        or model != settings.embedding_model
        or dimension != settings.embedding_dimensions
    ):
        raise HTTPException(
            status_code=422,
            detail=(
                "当前服务仅支持全局 Embedding 配置："
                f"embedding_provider=openai-compatible，"
                f"embedding_model={settings.embedding_model}，"
                f"embedding_dimension={settings.embedding_dimensions}"
            ),
        )
    return provider, model, dimension


@router.post("/assistants", status_code=status.HTTP_201_CREATED)
def create_assistant(
    request: AssistantCreateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """在当前公司创建一个 Assistant。"""
    company_id, actor = _identity(request, authorization, uid)
    row = _run(
        db,
        lambda: RagAdminRepository(db).create_assistant(
            company_id, request.assistant_key, request.name, actor
        ),
    )
    return {"item": row_dict(row)}


@router.post("/assistants/list")
def list_assistants(
    request: AdminListRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """列出当前公司的 Assistant。"""
    company_id, _ = _identity(request, authorization, uid)
    return _list_response(
        _run(db, lambda: RagAdminRepository(db).list_assistants(company_id, request.status))
    )


@router.post("/assistants/{assistant_id}/update")
def update_assistant(
    assistant_id: int,
    request: AssistantUpdateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """编辑 Assistant 名称或状态；assistant_key 创建后不可修改。"""
    company_id, _ = _identity(request, authorization, uid)
    values = {
        key: value
        for key, value in {"name": request.name, "status": request.status}.items()
        if value is not None
    }
    row = _run(
        db,
        lambda: RagAdminRepository(db).update_assistant(
            company_id, assistant_id, values
        ),
    )
    return {"item": row_dict(row)}


@router.post("/assistants/{assistant_id}/configs", status_code=status.HTTP_201_CREATED)
def create_config_version(
    assistant_id: int,
    request: AssistantConfigCreateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """为指定 Assistant 创建新的配置草稿版本。"""
    company_id, actor = _identity(request, authorization, uid)
    config = {
        "page_config": request.page_config,
        "model_config": request.model_settings,
        "retrieval_config": request.retrieval_config,
        "retrieval_scope": request.retrieval_scope,
        "knowledge_base_keys": request.knowledge_base_keys,
        "feature_flags": request.feature_flags,
    }
    row = _run(
        db,
        lambda: RagAdminRepository(db).create_config_version(
            company_id, assistant_id, config, actor
        ),
    )
    return {"item": _config_response(row)}


@router.post("/assistants/{assistant_id}/configs/list")
def list_config_versions(
    assistant_id: int,
    request: AdminContext,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """按版本倒序列出指定 Assistant 的配置。"""
    company_id, _ = _identity(request, authorization, uid)
    return _config_list_response(
        _run(db, lambda: RagAdminRepository(db).list_config_versions(company_id, assistant_id))
    )


@router.post("/assistants/{assistant_id}/configs/{config_id}/publish")
def publish_config(
    assistant_id: int,
    config_id: int,
    request: AdminPublishRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """发布目标配置并归档旧发布版本。"""
    company_id, actor = _identity(request, authorization, uid)
    row = _run(
        db,
        lambda: RagAdminRepository(db).publish_config(
            company_id, assistant_id, config_id, actor
        ),
    )
    return {"item": _config_response(row)}


@router.post("/assistants/{assistant_id}/prompts", status_code=status.HTTP_201_CREATED)
def create_prompt_version(
    assistant_id: int,
    request: PromptCreateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """为指定 Assistant 创建新的 Prompt 草稿版本。"""
    company_id, actor = _identity(request, authorization, uid)
    row = _run(
        db,
        lambda: RagAdminRepository(db).create_prompt_version(
            company_id,
            assistant_id,
            request.prompt_key,
            request.variant,
            request.content,
            request.model_overrides,
            actor,
        ),
    )
    return {"item": row_dict(row)}


@router.post("/assistants/{assistant_id}/prompts/list")
def list_prompt_versions(
    assistant_id: int,
    request: PromptListRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """按用途和变体列出指定 Assistant 的 Prompt 版本。"""
    company_id, _ = _identity(request, authorization, uid)
    return _list_response(
        _run(
            db,
            lambda: RagAdminRepository(db).list_prompt_versions(
                company_id, assistant_id, request.prompt_key, request.variant
            ),
        )
    )


@router.post("/assistants/{assistant_id}/prompts/{prompt_id}/publish")
def publish_prompt(
    assistant_id: int,
    prompt_id: int,
    request: AdminPublishRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """发布目标 Prompt 并归档同用途旧版本。"""
    company_id, actor = _identity(request, authorization, uid)
    row = _run(
        db,
        lambda: RagAdminRepository(db).publish_prompt(
            company_id, assistant_id, prompt_id, actor
        ),
    )
    return {"item": row_dict(row)}


@router.post("/knowledge-bases", status_code=status.HTTP_201_CREATED)
def create_knowledge_base(
    request: KnowledgeBaseCreateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """使用当前 Embedding 配置创建公司知识库。"""
    company_id, actor = _identity(request, authorization, uid)
    # Collection 的模型和维度必须与当前进程一致，防止创建后无法写入向量。
    embedding_provider, embedding_model, embedding_dimension = (
        _knowledge_embedding_config(request)
    )
    # Collection 名称由可信 company_id 和稳定 knowledge_key 计算，前端不能指定。
    values = {
        "knowledge_key": request.knowledge_key,
        "name": request.name,
        "description": request.description or None,
        "milvus_collection": milvus_service.collection_name(
            company_id=company_id, knowledge_base_key=request.knowledge_key
        ),
        "embedding_provider": embedding_provider,
        "embedding_model": embedding_model,
        "embedding_dimension": embedding_dimension,
        "chunk_size": request.chunk_size,
        "chunk_overlap": request.chunk_overlap,
        "default_top_k": request.default_top_k,
        "default_score_threshold": request.default_score_threshold,
        "permission_config_json": request.permission_config or None,
        "created_by": actor or None,
    }
    row = _run(
        db, lambda: RagAdminRepository(db).create_knowledge_base(company_id, values)
    )
    return {"item": row_dict(row)}


@router.post("/knowledge-bases/list")
def list_knowledge_bases(
    request: AdminListRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """列出当前公司的知识库。"""
    company_id, _ = _identity(request, authorization, uid)
    return _list_response(
        _run(db, lambda: RagAdminRepository(db).list_knowledge_bases(company_id, request.status))
    )


@router.post("/knowledge-bases/{knowledge_base_id}/update")
def update_knowledge_base(
    knowledge_base_id: int,
    request: KnowledgeBaseUpdateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """编辑知识库业务参数，保留 Collection、模型和向量维度不变。"""
    company_id, _ = _identity(request, authorization, uid)
    # 仅传入请求实际提交的可变字段，未提交字段继续保留数据库原值。
    values = {
        key: value
        for key, value in {
            "name": request.name,
            "description": request.description,
            "status": request.status,
            "chunk_size": request.chunk_size,
            "chunk_overlap": request.chunk_overlap,
            "default_top_k": request.default_top_k,
            "default_score_threshold": request.default_score_threshold,
            "permission_config_json": request.permission_config,
        }.items()
        if value is not None
    }
    # 空字符串或空对象表示主动清空可选字段，而不是忽略本次修改。
    if "description" in values:
        values["description"] = values["description"] or None
    if "permission_config_json" in values:
        values["permission_config_json"] = values["permission_config_json"] or None
    row = _run(
        db,
        lambda: RagAdminRepository(db).update_knowledge_base(
            company_id, knowledge_base_id, values
        ),
    )
    return {"item": row_dict(row)}


@router.post("/data-sources", status_code=status.HTTP_201_CREATED)
def create_data_source(
    request: DataSourceCreateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """创建只保存非敏感配置的数据源。"""
    company_id, actor = _identity(request, authorization, uid)
    values = {
        "source_key": request.source_key,
        "name": request.name,
        "source_type": request.source_type,
        "config_json": request.config or None,
        "credentials_ref": request.credentials_ref or None,
        "sync_config_json": request.sync_config or None,
        "created_by": actor or None,
    }
    row = _run(db, lambda: RagAdminRepository(db).create_data_source(company_id, values))
    return {"item": row_dict(row)}


@router.post("/data-sources/list")
def list_data_sources(
    request: AdminListRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """列出当前公司的数据源。"""
    company_id, _ = _identity(request, authorization, uid)
    return _list_response(
        _run(db, lambda: RagAdminRepository(db).list_data_sources(company_id, request.status))
    )


@router.post("/data-sources/{data_source_id}/update")
def update_data_source(
    data_source_id: int,
    request: DataSourceUpdateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """编辑数据源可变字段；敏感凭据仍只能通过 credentials_ref 引用。"""
    company_id, _ = _identity(request, authorization, uid)
    # source_key 和 source_type 不进入更新集合，避免已有绑定突然改变语义。
    values = {
        key: value
        for key, value in {
            "name": request.name,
            "status": request.status,
            "config_json": request.config,
            "credentials_ref": request.credentials_ref,
            "sync_config_json": request.sync_config,
        }.items()
        if value is not None
    }
    # 空对象/空字符串是明确的清空指令，统一转换为数据库 NULL。
    for key in ("config_json", "sync_config_json", "credentials_ref"):
        if key in values:
            values[key] = values[key] or None
    row = _run(
        db,
        lambda: RagAdminRepository(db).update_data_source(
            company_id, data_source_id, values
        ),
    )
    return {"item": row_dict(row)}


@router.post("/bindings/assistant-knowledge-base")
def bind_assistant_knowledge_base(
    request: AssistantKnowledgeBaseBindRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """创建或更新当前公司的 Assistant-知识库绑定。"""
    company_id, _ = _identity(request, authorization, uid)
    values = {
        "assistant_id": request.assistant_id,
        "knowledge_base_id": request.knowledge_base_id,
        "enabled": request.enabled,
        "priority": request.priority,
        "retrieval_config_json": request.retrieval_config or None,
        "permission_filter_json": request.permission_filter or None,
    }
    row = _run(
        db,
        lambda: RagAdminRepository(db).bind_assistant_knowledge_base(company_id, values),
    )
    return {"item": row_dict(row)}


@router.post("/bindings/assistant-knowledge-base/list")
def list_assistant_knowledge_base_bindings(
    request: AssistantKnowledgeBaseListRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """列出当前公司内的 Assistant-知识库绑定关系。"""
    company_id, _ = _identity(request, authorization, uid)
    rows = _run(
        db,
        lambda: RagAdminRepository(db).list_assistant_knowledge_base_bindings(
            company_id,
            assistant_id=request.assistant_id,
            knowledge_base_id=request.knowledge_base_id,
            enabled=request.enabled,
        ),
    )
    return _list_response(rows)


@router.post("/bindings/knowledge-base-source")
def bind_knowledge_base_source(
    request: KnowledgeBaseSourceBindRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """创建或更新当前公司的知识库-数据源绑定。"""
    company_id, _ = _identity(request, authorization, uid)
    values = {
        "knowledge_base_id": request.knowledge_base_id,
        "data_source_id": request.data_source_id,
        "enabled": request.enabled,
        "priority": request.priority,
        "import_config_json": request.import_config or None,
    }
    row = _run(
        db,
        lambda: RagAdminRepository(db).bind_knowledge_base_source(company_id, values),
    )
    return {"item": row_dict(row)}


@router.post("/bindings/knowledge-base-source/list")
def list_knowledge_base_source_bindings(
    request: KnowledgeBaseSourceListRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """列出当前公司内的知识库-数据源绑定关系。"""
    company_id, _ = _identity(request, authorization, uid)
    rows = _run(
        db,
        lambda: RagAdminRepository(db).list_knowledge_base_source_bindings(
            company_id,
            knowledge_base_id=request.knowledge_base_id,
            data_source_id=request.data_source_id,
            enabled=request.enabled,
        ),
    )
    return _list_response(rows)

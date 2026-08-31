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
    DataSourceCreateRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseSourceBindRequest,
    PromptCreateRequest,
    PromptListRequest,
)
from ai_erp_rag_assistant.app.services.milvus_service import milvus_service
from ai_erp_rag_assistant.app.tools.erp_tools import get_current_user


router = APIRouter(prefix="/rag/admin", tags=["RAG Admin"])
T = TypeVar("T")


def _required_db() -> Generator[Session, None, None]:
    try:
        yield from get_db_session()
    except DatabaseNotConfiguredError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


DbSession = Annotated[Session, Depends(_required_db)]


def _identity(
    request: AdminContext, authorization: str | None, uid: str | None
) -> tuple[str, str]:
    request = request.model_copy(
        update={
            "authorization": request.authorization or authorization or "",
            "uid": request.uid or uid or "",
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
    if not company_id or company_id != request.company_id.strip():
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    actor = str(user.get("uid") or user.get("user_id") or request.uid or request.user_id).strip()
    return company_id, actor


def _run(session: Session, operation: Callable[[], T]) -> T:
    try:
        return operation()
    except AdminNotFoundError as exc:
        session.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="业务标识或版本已存在") from exc
    except SQLAlchemyError as exc:
        session.rollback()
        raise HTTPException(status_code=503, detail="MySQL 操作失败") from exc


def _list_response(rows: list[Any]) -> dict[str, Any]:
    items = [row_dict(row) for row in rows]
    return {"items": items, "count": len(items)}


def _knowledge_embedding_config(
    request: KnowledgeBaseCreateRequest,
) -> tuple[str, str, int]:
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
    company_id, _ = _identity(request, authorization, uid)
    return _list_response(
        _run(db, lambda: RagAdminRepository(db).list_assistants(company_id, request.status))
    )


@router.post("/assistants/{assistant_id}/configs", status_code=status.HTTP_201_CREATED)
def create_config_version(
    assistant_id: int,
    request: AssistantConfigCreateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    company_id, actor = _identity(request, authorization, uid)
    config = {
        "page_config": request.page_config,
        "model_config": request.model_settings,
        "retrieval_config": request.retrieval_config,
        "feature_flags": request.feature_flags,
    }
    row = _run(
        db,
        lambda: RagAdminRepository(db).create_config_version(
            company_id, assistant_id, config, actor
        ),
    )
    return {"item": row_dict(row)}


@router.post("/assistants/{assistant_id}/configs/list")
def list_config_versions(
    assistant_id: int,
    request: AdminContext,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    company_id, _ = _identity(request, authorization, uid)
    return _list_response(
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
    company_id, actor = _identity(request, authorization, uid)
    row = _run(
        db,
        lambda: RagAdminRepository(db).publish_config(
            company_id, assistant_id, config_id, actor
        ),
    )
    return {"item": row_dict(row)}


@router.post("/assistants/{assistant_id}/prompts", status_code=status.HTTP_201_CREATED)
def create_prompt_version(
    assistant_id: int,
    request: PromptCreateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
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
    company_id, actor = _identity(request, authorization, uid)
    embedding_provider, embedding_model, embedding_dimension = (
        _knowledge_embedding_config(request)
    )
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
    company_id, _ = _identity(request, authorization, uid)
    return _list_response(
        _run(db, lambda: RagAdminRepository(db).list_knowledge_bases(company_id, request.status))
    )


@router.post("/data-sources", status_code=status.HTTP_201_CREATED)
def create_data_source(
    request: DataSourceCreateRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
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
    company_id, _ = _identity(request, authorization, uid)
    return _list_response(
        _run(db, lambda: RagAdminRepository(db).list_data_sources(company_id, request.status))
    )


@router.post("/bindings/assistant-knowledge-base")
def bind_assistant_knowledge_base(
    request: AssistantKnowledgeBaseBindRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
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


@router.post("/bindings/knowledge-base-source")
def bind_knowledge_base_source(
    request: KnowledgeBaseSourceBindRequest,
    db: DbSession,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
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

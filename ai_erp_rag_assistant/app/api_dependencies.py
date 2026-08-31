"""Shared authentication and runtime dependencies for HTTP route modules."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.rag_admin_repository import (
    AdminNotFoundError,
    RagAdminRepository,
    RagRuntimeConfig,
)
from ai_erp_rag_assistant.app.services.milvus_service import milvus_service
from ai_erp_rag_assistant.app.tools.erp_tools import get_current_user


def with_header_identity(request: Any, authorization: str | None, uid: str | None) -> Any:
    """Merge trusted transport headers into an API request model."""
    return request.model_copy(
        update={
            "authorization": request.authorization or authorization or "",
            "uid": request.uid or uid or "",
        }
    )


def erp_user(request: Any) -> dict[str, Any]:
    """Resolve the current user through the configured ERP identity provider."""
    return get_current_user(
        request.user_id,
        uid=request.uid,
        authorization=request.authorization,
        company_id=request.company_id,
        department=request.department,
    )


def persistent_identity(
    request: Any,
    authorization: str | None,
    uid: str | None,
) -> tuple[Any, dict[str, Any], str, str]:
    """Use verified ERP identity to determine durable session ownership."""
    request = with_header_identity(request, authorization, uid)
    try:
        user = erp_user(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    company_id = str(user.get("company_id") or "").strip()
    if not company_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的 company_id")
    if request.company_id and request.company_id.strip() != company_id:
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    # Page-supplied user_id is not an isolation boundary; prefer verified ERP IDs.
    user_id = str(user.get("uid") or request.uid or user.get("user_id") or request.user_id).strip()
    if not user_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的用户ID")
    return request, user, company_id, user_id


def rag_identity(
    request: Any,
    authorization: str | None,
    uid: str | None,
) -> tuple[Any, str, str]:
    """Verify tenant ownership before any RAG read or write operation."""
    request = with_header_identity(request, authorization, uid)
    try:
        user = erp_user(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    company_id = str(user.get("company_id") or "").strip()
    requested_company = request.company_id.strip()
    if not company_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的 company_id")
    if requested_company != company_id:
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    return request, company_id, str(user.get("department") or request.department).strip()


def rag_runtime_config(
    db: Session | None,
    *,
    company_id: str,
    knowledge_base_key: str,
    assistant_key: str,
) -> RagRuntimeConfig:
    """Resolve DB-backed RAG settings, falling back to process defaults."""
    fallback = RagRuntimeConfig(
        collection=milvus_service.collection_name(
            company_id=company_id, knowledge_base_key=knowledge_base_key
        ),
        chunk_size=get_settings().rag_chunk_size,
        chunk_overlap=get_settings().rag_chunk_overlap,
    )
    if db is None:
        return fallback
    try:
        configured = RagAdminRepository(db).runtime_config(
            company_id, knowledge_base_key, assistant_key
        )
        return RagRuntimeConfig(
            collection=configured.collection or fallback.collection,
            system_context=configured.system_context,
            model_overrides=configured.model_overrides,
            chunk_size=configured.chunk_size or fallback.chunk_size,
            chunk_overlap=(
                configured.chunk_overlap
                if configured.chunk_overlap is not None
                else fallback.chunk_overlap
            ),
            top_k=configured.top_k,
            score_threshold=configured.score_threshold,
        )
    except AdminNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="MySQL 读取 RAG 配置失败") from exc

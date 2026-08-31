"""API composition root and shared request helpers.

Endpoint implementations live in :mod:`app.routes`; this module keeps the
stable ``app.api`` import surface used by the application and tests.
"""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from typing import Any

import langsmith.anonymizer as langsmith_anonymizer
from fastapi import APIRouter, HTTPException
from langsmith import Client
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.rag_admin_api import router as rag_admin_router
from ai_erp_rag_assistant.app.rag_admin_repository import (
    AdminNotFoundError,
    RagAdminRepository,
    RagRuntimeConfig,
)
from ai_erp_rag_assistant.app.services.approval_form_service import build_form_schema
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event
from ai_erp_rag_assistant.app.services.document_ingest_service import build_chunk_rows
from ai_erp_rag_assistant.app.services.milvus_service import milvus_service
from ai_erp_rag_assistant.app.services.model_service import model_service
from ai_erp_rag_assistant.app.services.session_repository import session_repository
from ai_erp_rag_assistant.app.tools.erp_tools import (
    get_approval_field_options,
    get_approval_template,
    get_current_user,
    list_approval_templates,
)
from ai_erp_rag_assistant.scripts.ingest_pdf import infer_title, split_text


# ``/api`` is the public prefix; individual modules only own their feature paths.
router = APIRouter(prefix="/api")
workflow = None
stateless_workflow = None

_SENSITIVE_TRACE_FIELDS = {
    "api_key",
    "authorization",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "token",
}


def _identity_anonymizer(data: Any) -> Any:
    return data


# Older LangSmith releases do not expose create_secret_anonymizer; field-level
# redaction remains enabled in either case.
_secret_anonymizer_factory: Any = getattr(
    langsmith_anonymizer, "create_secret_anonymizer", None
)
_secret_anonymizer = (
    _secret_anonymizer_factory()
    if callable(_secret_anonymizer_factory)
    else _identity_anonymizer
)
_field_anonymizer = langsmith_anonymizer.create_anonymizer(
    lambda value, path: (
        "[REDACTED]"
        if path and str(path[-1]).lower() in _SENSITIVE_TRACE_FIELDS
        else value
    ),
    max_depth=24,
)


def _anonymize_trace(data: Any) -> Any:
    return _field_anonymizer(_secret_anonymizer(data))


@lru_cache(maxsize=1)
def _langsmith_client() -> Client | None:
    settings = get_settings()
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return None
    return Client(api_key=settings.langsmith_api_key, anonymizer=_anonymize_trace)


def _thread_id(request: Any) -> str:
    tenant = request.company_id.strip() or "default"
    principal = request.uid.strip() or request.user_id.strip()
    session = request.session_id.strip()
    digest = sha256(f"{tenant}\x1f{principal}\x1f{session}".encode()).hexdigest()
    return f"erp-rag:{digest}"


def _with_header_identity(request: Any, authorization: str | None, uid: str | None) -> Any:
    return request.model_copy(
        update={
            "authorization": request.authorization or authorization or "",
            "uid": request.uid or uid or "",
        }
    )


def _erp_user(request: Any) -> dict[str, Any]:
    return get_current_user(
        request.user_id,
        uid=request.uid,
        authorization=request.authorization,
        company_id=request.company_id,
        department=request.department,
    )


def _persistent_identity(
    request: Any,
    authorization: str | None,
    uid: str | None,
) -> tuple[Any, dict[str, Any], str, str]:
    """Use verified ERP identity to determine durable session ownership."""
    request = _with_header_identity(request, authorization, uid)
    try:
        user = _erp_user(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    company_id = str(user.get("company_id") or "").strip()
    if not company_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的 company_id")
    if request.company_id and request.company_id.strip() != company_id:
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    # The page-supplied user_id is not an isolation boundary; prefer verified ERP IDs.
    user_id = str(user.get("uid") or request.uid or user.get("user_id") or request.user_id).strip()
    if not user_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的用户ID")
    return request, user, company_id, user_id


def _rag_identity(
    request: Any,
    authorization: str | None,
    uid: str | None,
) -> tuple[Any, str, str]:
    request = _with_header_identity(request, authorization, uid)
    try:
        user = _erp_user(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    company_id = str(user.get("company_id") or "").strip()
    requested_company = request.company_id.strip()
    if not company_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的 company_id")
    if requested_company != company_id:
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    return request, company_id, str(user.get("department") or request.department).strip()


def _rag_runtime_config(
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


# Import feature routers after shared helpers so route modules can reference the
# compatibility surface above without introducing an initialization cycle.
from ai_erp_rag_assistant.app.routes import approvals, chat as chat_routes, rag, sessions

# The chat module owns workflow construction; these aliases preserve the old
# ``app.api.workflow`` integration point without creating a second graph.
workflow = chat_routes.workflow
stateless_workflow = chat_routes.stateless_workflow

router.include_router(rag_admin_router)
router.include_router(chat_routes.router)
router.include_router(rag.router)
router.include_router(sessions.router)
router.include_router(approvals.router)

# Preserve the historical ``app.api.<endpoint>`` imports for integrations/tests.
chat = chat_routes.chat
rag_search = rag.rag_search
rag_chat = rag.rag_chat
rag_ingest_text = rag.rag_ingest_text
rag_ingest_pdf = rag.rag_ingest_pdf
rag_ingest_document = rag.rag_ingest_document
_rag_rows_from_text = rag._rag_rows_from_text
_rag_rows_from_pdf = rag._rag_rows_from_pdf
session_list = sessions.session_list
session_messages = sessions.session_messages
approval_templates = approvals.approval_templates
approval_form_schema = approvals.approval_form_schema
approval_field_options = approvals.approval_field_options

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from typing import Annotated, Any, cast

import langsmith.anonymizer as langsmith_anonymizer
from fastapi import APIRouter, Depends, Header, HTTPException, Request
from langchain_core.runnables import RunnableConfig
from langsmith import Client, tracing_context
from starlette.concurrency import run_in_threadpool

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.database import get_optional_db_session
from ai_erp_rag_assistant.app.graph.state import ErpRagState, initial_state
from ai_erp_rag_assistant.app.graph.workflow import create_workflow
from ai_erp_rag_assistant.app.schemas import (
    ApprovalFieldOptionsRequest,
    ApprovalFormSchemaRequest,
    ApprovalTemplatesRequest,
    ChatRequest,
    ChatResponse,
    RagChatRequest,
    RagChatResponse,
    RagEvidenceResponse,
    RagIngestResponse,
    RagSearchRequest,
    RagTextIngestRequest,
    SessionListRequest,
    SessionMessagesRequest,
)
from ai_erp_rag_assistant.app.rag_admin_repository import (
    AdminNotFoundError,
    RagAdminRepository,
    RagRuntimeConfig,
)
from ai_erp_rag_assistant.app.rag_admin_api import router as rag_admin_router
from ai_erp_rag_assistant.app.services.approval_form_service import build_form_schema
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event
from ai_erp_rag_assistant.app.services.document_ingest_service import (
    DocumentParseError,
    build_chunk_rows,
)
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
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session


router = APIRouter(prefix="/api")
router.include_router(rag_admin_router)
workflow = create_workflow()
stateless_workflow = create_workflow(with_checkpointer=False)

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


# 较旧的 LangSmith 没有 create_secret_anonymizer；字段名脱敏仍始终启用。
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


def _thread_id(request: ChatRequest) -> str:
    tenant = request.company_id.strip() or "default"
    principal = request.uid.strip() or request.user_id.strip()
    session = request.session_id.strip()
    digest = sha256(f"{tenant}\x1f{principal}\x1f{session}".encode()).hexdigest()
    return f"erp-rag:{digest}"


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> ChatResponse:
    if authorization or uid:
        request = request.model_copy(update={
            "authorization": request.authorization or authorization or "",
            "uid": request.uid or uid or "",
        })
    settings = get_settings()
    assistant_key = request.assistant_key.strip() or settings.assistant_key
    persistent_user: dict[str, Any] = {}
    if session_repository.enabled:
        request, persistent_user, resolved_company, persistent_user_id = _persistent_identity(
            request, None, None
        )
        request = request.model_copy(
            update={"company_id": resolved_company, "user_id": persistent_user_id}
        )
        cached = session_repository.cached_response(
            company_id=resolved_company,
            assistant_key=assistant_key,
            user_id=request.user_id,
            session_key=request.session_id,
            request_id=request.request_id,
        )
        if cached:
            return ChatResponse.model_validate(cached)
    thread_id = _thread_id(request)
    config: RunnableConfig = {
        "configurable": {"thread_id": thread_id},
        "run_name": "erp-rag-chat",
        "tags": ["ai-erp-rag-assistant"],
        "metadata": {"thread_id": thread_id, "transport": "fastapi"},
    }
    prior: ErpRagState = {}
    if not request.reset:
        if session_repository.enabled:
            prior = cast(
                ErpRagState,
                session_repository.load_state(
                    company_id=request.company_id,
                    assistant_key=assistant_key,
                    user_id=request.user_id,
                    session_key=request.session_id,
                ),
            )
        else:
            snapshot = workflow.get_state(config)
            if snapshot and snapshot.values:
                prior = cast(ErpRagState, dict(snapshot.values))
    state = initial_state(
        request.session_id,
        request.user_id,
        request.message,
        uid=request.uid,
        authorization=request.authorization,
        company_id=request.company_id,
        department=request.department,
        confirm=request.confirm,
        confirm_preview_id=request.preview_id,
        confirm_preview_version=request.preview_version,
        confirm_preview_hash=request.preview_hash,
        form_values=request.form_values,
        selected_assignees=request.selected_assignees,
        prior=prior,
    )
    if persistent_user:
        state["user_context"] = persistent_user
    try:
        client = _langsmith_client()
        with tracing_context(
            enabled=client is not None,
            client=client,
            project_name=settings.langsmith_project,
        ):
            runtime_workflow = stateless_workflow if session_repository.enabled else workflow
            result = runtime_workflow.invoke(state, config=config)
    except Exception as exc:
        # Keep the failure visible in the demo instead of returning a fake answer.
        result = {
            **state,
            "assistant_message": f"执行失败：{exc}",
            "errors": [str(exc)],
            "tool_calls": [{"tool": "system.error", "error": str(exc)}],
        }
    erp_data = result.get("erp_data", {})
    response = ChatResponse(
        message=result.get("assistant_message", ""),
        route=result.get("route", "unknown"),
        plan=result.get("plan", {}),
        tool_calls=result.get("tool_calls", []),
        evidence=result.get("evidence", []),
        erp_data=erp_data,
        form_schema=result.get("form_schema") or None,
        preview=result.get("preview") or None,
        errors=result.get("errors", []),
        pending_question=result.get("pending_question", ""),
        workflow_status=str(result.get("workflow_status") or "idle"),
        erp_mode=str(erp_data.get("erp_mode") or result.get("user_context", {}).get("erp_mode") or get_settings().erp_mode),
        erp_write_mode=str(erp_data.get("erp_write_mode") or get_settings().erp_write_mode),
    )
    if session_repository.enabled:
        try:
            session_repository.save_exchange(
                company_id=request.company_id,
                assistant_key=assistant_key,
                session_key=request.session_id,
                user_id=request.user_id,
                erp_uid=request.uid,
                request_id=request.request_id,
                user_message=request.message,
                state=dict(result),
                response=response.model_dump(),
            )
        except Exception as exc:
            write_audit_event(
                "session.persistence.error",
                {
                    "company_id": request.company_id,
                    "assistant_key": assistant_key,
                    "session_id": request.session_id,
                    "request_id": request.request_id,
                    "error": str(exc)[:300],
                },
            )
            raise HTTPException(status_code=503, detail=f"会话持久化失败：{exc}") from exc
    return response


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
    """使用 ERP 已验证身份确定长期会话的公司和用户归属。"""

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
    # user_id 来自页面，不能作为数据隔离依据；优先使用 ERP 返回或已验证的 UID。
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


def _rag_rows_from_text(request: RagTextIngestRequest) -> list[dict[str, Any]]:
    company_id = request.company_id.strip()
    source = request.source.strip()
    if not company_id:
        raise HTTPException(status_code=422, detail="company_id 不能为空")
    if not source:
        raise HTTPException(status_code=422, detail="source 不能为空")
    if request.chunk_overlap >= request.chunk_size:
        raise HTTPException(status_code=422, detail="chunk_overlap 必须小于 chunk_size")
    chunks = split_text(request.content, request.chunk_size, request.chunk_overlap)
    if not chunks:
        raise HTTPException(status_code=422, detail="content 不能只包含空白字符")
    title = request.title.strip() or source.rsplit("/", 1)[-1]
    return [
        {
            "chunk_id": f"{company_id}:{request.knowledge_base_key.strip() or 'default'}:{sha256(f'{source}:{index}:{chunk}'.encode()).hexdigest()[:32]}",
            "text": chunk,
            "source": source,
            "page": 1,
            "title": title,
            "company_id": company_id,
            "department": request.department,
            "version": request.version,
            "effective_date": request.effective_date,
            "is_active": True,
            "permission_tags": request.permission_tags,
        }
        for index, chunk in enumerate(chunks, start=1)
    ]


def _rag_rows_from_pdf(
    content: bytes,
    *,
    company_id: str,
    source: str,
    knowledge_base_key: str,
    department: str,
    version: str,
    effective_date: str,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[list[dict[str, Any]], list[int]]:
    from io import BytesIO

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(content))
    rows: list[dict[str, Any]] = []
    empty_pages: list[int] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
        if not page_text.strip():
            empty_pages.append(page_number)
            continue
        chunks = split_text(page_text, chunk_size, chunk_overlap)
        for chunk_number, chunk in enumerate(chunks, start=1):
            rows.append(
                {
                    "chunk_id": f"{company_id}:{knowledge_base_key or 'default'}:{sha256(f'{source}:{page_number}:{chunk_number}:{chunk}'.encode()).hexdigest()[:32]}",
                    "text": chunk,
                    "source": source,
                    "page": page_number,
                    "title": infer_title(chunk, source.rsplit("/", 1)[-1]),
                    "company_id": company_id,
                    "department": department,
                    "version": version,
                    "effective_date": effective_date,
                    "is_active": True,
                    "permission_tags": [],
                }
            )
    return rows, empty_pages


@router.post("/rag/search", response_model=RagEvidenceResponse)
def rag_search(
    request: RagSearchRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagEvidenceResponse:
    try:
        request, company_id, department = _rag_identity(request, authorization, uid)
        if not company_id or not request.query.strip():
            raise ValueError("company_id 和 query 不能为空")
        knowledge_base_key = request.knowledge_base_key.strip()
        runtime = _rag_runtime_config(
            db,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            assistant_key=request.assistant_key.strip(),
        )
        evidence = milvus_service.search(
            request.query,
            company_id=company_id,
            department=department,
            permission_tags=request.permission_tags,
            top_k=request.top_k or runtime.top_k or 5,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
            min_score=runtime.score_threshold,
        )
        return RagEvidenceResponse(
            evidence=evidence,
            count=len(evidence),
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            collection=runtime.collection,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/rag/chat", response_model=RagChatResponse)
def rag_chat(
    request: RagChatRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagChatResponse:
    try:
        request, company_id, department = _rag_identity(request, authorization, uid)
        if not company_id or not request.query.strip():
            raise ValueError("company_id 和 query 不能为空")
        knowledge_base_key = request.knowledge_base_key.strip()
        runtime = _rag_runtime_config(
            db,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            assistant_key=request.assistant_key.strip(),
        )
        evidence = milvus_service.search(
            request.query,
            company_id=company_id,
            department=department,
            permission_tags=request.permission_tags,
            top_k=request.top_k or runtime.top_k or 5,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
            min_score=runtime.score_threshold,
        )
        system_context = "\n\n".join(
            value for value in (runtime.system_context, request.system_context.strip()) if value
        )
        answer = model_service.answer(
            request.query,
            route="knowledge",
            evidence=evidence,
            system_context=system_context,
            model_overrides=runtime.model_overrides,
        )
        return RagChatResponse(
            message=answer,
            evidence=evidence,
            count=len(evidence),
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            collection=runtime.collection,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/rag/ingest/text", response_model=RagIngestResponse)
def rag_ingest_text(
    request: RagTextIngestRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagIngestResponse:
    request, company_id, department = _rag_identity(request, authorization, uid)
    request = request.model_copy(update={"company_id": company_id, "department": department})
    rows = _rag_rows_from_text(request)
    knowledge_base_key = request.knowledge_base_key.strip()
    runtime = _rag_runtime_config(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        assistant_key="",
    )
    try:
        inserted = milvus_service.upsert_chunks(
            rows,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RagIngestResponse(
        source=request.source,
        chunk_count=len(rows),
        inserted_count=inserted,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        collection=runtime.collection,
    )


@router.post("/rag/ingest/pdf", response_model=RagIngestResponse)
async def rag_ingest_pdf(
    request: Request,
    company_id: str,
    user_id: str = "",
    source: str = "uploaded.pdf",
    knowledge_base_key: str = "",
    department: str = "",
    version: str = "",
    effective_date: str = "",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagIngestResponse:
    """Ingest one PDF sent as an application/pdf request body."""
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].lower()
    if content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="PDF 导入必须使用 Content-Type: application/pdf")
    try:
        user = get_current_user(
            user_id,
            uid=uid or "",
            authorization=authorization or "",
            company_id=company_id,
            department=department,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    resolved_company = str(user.get("company_id") or "").strip()
    if not resolved_company or resolved_company != company_id.strip():
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    source = source.strip()
    if not source:
        raise HTTPException(status_code=422, detail="source 不能为空")
    company_id = resolved_company
    department = str(user.get("department") or department).strip()
    knowledge_base_key = knowledge_base_key.strip()
    runtime = _rag_runtime_config(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        assistant_key="",
    )
    # 未传切分参数时，优先采用知识库后台配置；没有 MySQL 配置则使用项目默认值。
    chunk_size = chunk_size if chunk_size is not None else (runtime.chunk_size or get_settings().rag_chunk_size)
    chunk_overlap = (
        chunk_overlap
        if chunk_overlap is not None
        else (runtime.chunk_overlap if runtime.chunk_overlap is not None else get_settings().rag_chunk_overlap)
    )
    if not 100 <= chunk_size <= 4000 or not 0 <= chunk_overlap < chunk_size:
        raise HTTPException(status_code=422, detail="chunk_size 必须为 100..4000，chunk_overlap 必须小于 chunk_size")
    try:
        content = await request.body()
        if not content:
            raise ValueError("PDF 内容为空")
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("PDF 大小不能超过 20MB")
        # 接口仍同步返回；阻塞型 PDF 解析在线程池执行，避免占用事件循环。
        rows, empty_pages = await run_in_threadpool(
            _rag_rows_from_pdf,
            content,
            company_id=company_id,
            source=source,
            knowledge_base_key=knowledge_base_key,
            department=department,
            version=version,
            effective_date=effective_date,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not rows:
            raise ValueError("PDF 没有可提取文本；扫描件请先生成文字层")
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"PDF 解析失败：{exc}") from exc
    try:
        inserted = await run_in_threadpool(
            milvus_service.upsert_chunks,
            rows,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RagIngestResponse(
        source=source,
        chunk_count=len(rows),
        inserted_count=inserted,
        empty_pages=empty_pages,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        collection=runtime.collection,
    )


@router.post("/rag/ingest/document", response_model=RagIngestResponse)
async def rag_ingest_document(
    request: Request,
    company_id: str,
    source: str,
    user_id: str = "",
    knowledge_base_key: str = "",
    department: str = "",
    version: str = "",
    effective_date: str = "",
    title: str = "",
    permission_tags: str = "",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagIngestResponse:
    """同步导入一个原始文档，解析、切分、向量化并写入 Milvus。"""
    source = source.strip()
    if not source:
        raise HTTPException(status_code=422, detail="source 不能为空，需包含文档扩展名")
    try:
        user = get_current_user(
            user_id,
            uid=uid or "",
            authorization=authorization or "",
            company_id=company_id,
            department=department,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    resolved_company = str(user.get("company_id") or "").strip()
    if not resolved_company or resolved_company != company_id.strip():
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    company_id = resolved_company
    department = str(user.get("department") or department).strip()
    knowledge_base_key = knowledge_base_key.strip()
    runtime = _rag_runtime_config(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        assistant_key="",
    )
    # 未传切分参数时，优先采用知识库后台配置；没有 MySQL 配置则使用项目默认值。
    chunk_size = (
        chunk_size
        if chunk_size is not None
        else (getattr(runtime, "chunk_size", None) or get_settings().rag_chunk_size)
    )
    chunk_overlap = (
        chunk_overlap
        if chunk_overlap is not None
        else (
            getattr(runtime, "chunk_overlap", None)
            if getattr(runtime, "chunk_overlap", None) is not None
            else get_settings().rag_chunk_overlap
        )
    )
    if not 100 <= chunk_size <= 4000 or not 0 <= chunk_overlap < chunk_size:
        raise HTTPException(
            status_code=422,
            detail="chunk_size 必须为 100..4000，chunk_overlap 必须小于 chunk_size",
        )
    try:
        # 原始请求体避免 multipart 依赖；source 后缀决定解析器。
        content = await request.body()
        if len(content) > 20 * 1024 * 1024:
            raise DocumentParseError("文档大小不能超过 20MB")
        # 解析和切分属于阻塞型 CPU/文件操作，在线程池执行但仍等待完成后返回。
        rows, empty_pages = await run_in_threadpool(
            build_chunk_rows,
            content,
            company_id=company_id,
            source=source,
            knowledge_base_key=knowledge_base_key,
            department=department,
            version=version,
            effective_date=effective_date,
            permission_tags=[tag for tag in permission_tags.split(",") if tag.strip()],
            title=title,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
    except DocumentParseError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    try:
        # Embedding 和 Milvus 都是阻塞型网络调用；线程池不改变同步接口语义。
        inserted = await run_in_threadpool(
            milvus_service.upsert_chunks,
            rows,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    return RagIngestResponse(
        source=source,
        chunk_count=len(rows),
        inserted_count=inserted,
        empty_pages=empty_pages,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        collection=runtime.collection,
    )


@router.post("/sessions/list")
def session_list(
    request: SessionListRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """返回当前公司、Assistant 和 ERP 用户范围内的会话列表。"""

    if not session_repository.enabled:
        raise HTTPException(status_code=503, detail="长期会话未启用，请配置 AI_ERP_SESSION_STORE=mysql")
    request, _, company_id, user_id = _persistent_identity(request, authorization, uid)
    assistant_key = request.assistant_key.strip() or get_settings().assistant_key
    try:
        items, has_more = session_repository.list_sessions(
            company_id=company_id,
            assistant_key=assistant_key,
            user_id=user_id,
            status=request.status,
            page=request.page,
            page_size=request.page_size,
        )
        return {
            "items": items,
            "count": len(items),
            "page": request.page,
            "page_size": request.page_size,
            "has_more": has_more,
        }
    except Exception as exc:
        write_audit_event(
            "session.list.error",
            {"company_id": company_id, "assistant_key": assistant_key, "error": str(exc)[:300]},
        )
        raise HTTPException(status_code=503, detail=f"读取会话列表失败：{exc}") from exc


@router.post("/sessions/messages")
def session_messages(
    request: SessionMessagesRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    """按游标返回当前 ERP 用户拥有的单个会话消息。"""

    if not session_repository.enabled:
        raise HTTPException(status_code=503, detail="长期会话未启用，请配置 AI_ERP_SESSION_STORE=mysql")
    request, _, company_id, user_id = _persistent_identity(request, authorization, uid)
    assistant_key = request.assistant_key.strip() or get_settings().assistant_key
    try:
        items, has_more = session_repository.list_messages(
            company_id=company_id,
            assistant_key=assistant_key,
            user_id=user_id,
            session_key=request.session_id,
            before_seq=request.before_seq,
            page_size=request.page_size,
        )
        return {
            "items": items,
            "count": len(items),
            "session_id": request.session_id,
            "has_more": has_more,
            "next_before_seq": items[0]["message_seq"] if has_more and items else None,
        }
    except Exception as exc:
        write_audit_event(
            "session.messages.error",
            {
                "company_id": company_id,
                "assistant_key": assistant_key,
                "session_id": request.session_id,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(status_code=503, detail=f"读取会话消息失败：{exc}") from exc


@router.post("/approval/templates")
def approval_templates(
    request: ApprovalTemplatesRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    request = _with_header_identity(request, authorization, uid)
    try:
        user = _erp_user(request)
        items = list_approval_templates(
            request.query,
            str(user.get("company_id") or request.company_id),
            user=user,
        )
        return {
            "items": items,
            "count": len(items),
            "erp_mode": user.get("erp_mode"),
            "erp_write_mode": user.get("erp_write_mode"),
        }
    except Exception as exc:
        write_audit_event("approval.templates.error", {"user_id": request.user_id, "error": str(exc)[:300]})
        raise HTTPException(status_code=502, detail=str(exc)) from exc



@router.post("/approval/form-schema")
def approval_form_schema(
    request: ApprovalFormSchemaRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    request = _with_header_identity(request, authorization, uid)
    try:
        user = _erp_user(request)
        template = get_approval_template(
            request.template_id,
            str(user.get("company_id") or request.company_id),
            title=request.title,
            user=user,
        )
        return build_form_schema(template, request.values)
    except Exception as exc:
        write_audit_event(
            "approval.form_schema.error",
            {"template_id": request.template_id, "user_id": request.user_id, "error": str(exc)[:300]},
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/approval/options")
def approval_field_options(
    request: ApprovalFieldOptionsRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> dict[str, Any]:
    request = _with_header_identity(request, authorization, uid)
    try:
        user = _erp_user(request)
        return get_approval_field_options(
            request.template_id,
            request.field_key,
            str(user.get("company_id") or request.company_id),
            title=request.title,
            keyword=request.keyword,
            page=request.page,
            page_size=request.page_size,
            user=user,
        )
    except Exception as exc:
        write_audit_event(
            "approval.options.error",
            {
                "template_id": request.template_id,
                "field_key": request.field_key,
                "user_id": request.user_id,
                "error": str(exc)[:300],
            },
        )
        raise HTTPException(status_code=502, detail=str(exc)) from exc

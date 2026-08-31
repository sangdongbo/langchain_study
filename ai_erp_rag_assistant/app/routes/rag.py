"""RAG search and synchronous document ingestion endpoints."""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ai_erp_rag_assistant.app import api as api_module
from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.database import get_optional_db_session
from ai_erp_rag_assistant.app.rag_admin_repository import RagRuntimeConfig
from ai_erp_rag_assistant.app.schemas import (
    RagChatRequest,
    RagChatResponse,
    RagEvidenceResponse,
    RagIngestResponse,
    RagSearchRequest,
    RagTextIngestRequest,
)
from ai_erp_rag_assistant.app.services.document_ingest_service import (
    DocumentParseError,
    build_chunk_rows,
)
from ai_erp_rag_assistant.scripts.ingest_pdf import infer_title, split_text


router = APIRouter(tags=["RAG"])


def _rag_rows_from_text(request: RagTextIngestRequest) -> list[dict[str, Any]]:
    """Build tenant-scoped chunk rows for the text ingestion endpoint."""
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
    """Extract PDF pages while retaining page and tenant metadata."""
    # Import here so parser tests can replace pypdf without loading a real PDF.
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
        request, company_id, department = api_module._rag_identity(request, authorization, uid)
        if not company_id or not request.query.strip():
            raise ValueError("company_id 和 query 不能为空")
        knowledge_base_key = request.knowledge_base_key.strip()
        runtime = api_module._rag_runtime_config(
            db,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            assistant_key=request.assistant_key.strip(),
        )
        evidence = api_module.milvus_service.search(
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
        request, company_id, department = api_module._rag_identity(request, authorization, uid)
        if not company_id or not request.query.strip():
            raise ValueError("company_id 和 query 不能为空")
        knowledge_base_key = request.knowledge_base_key.strip()
        runtime = api_module._rag_runtime_config(
            db,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            assistant_key=request.assistant_key.strip(),
        )
        evidence = api_module.milvus_service.search(
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
        answer = api_module.model_service.answer(
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
    request, company_id, department = api_module._rag_identity(request, authorization, uid)
    request = request.model_copy(update={"company_id": company_id, "department": department})
    rows = _rag_rows_from_text(request)
    knowledge_base_key = request.knowledge_base_key.strip()
    runtime = api_module._rag_runtime_config(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        assistant_key="",
    )
    try:
        inserted = api_module.milvus_service.upsert_chunks(
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


def _resolve_ingest_identity(
    user_id: str,
    company_id: str,
    department: str,
    authorization: str | None,
    uid: str | None,
) -> tuple[str, str]:
    try:
        user = api_module.get_current_user(
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
    return resolved_company, str(user.get("department") or department).strip()


def _ingest_runtime(
    db: Session | None,
    *,
    company_id: str,
    knowledge_base_key: str,
    chunk_size: int | None,
    chunk_overlap: int | None,
) -> tuple[RagRuntimeConfig, int, int]:
    runtime = api_module._rag_runtime_config(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        assistant_key="",
    )
    resolved_chunk_size = (
        chunk_size if chunk_size is not None else (getattr(runtime, "chunk_size", None) or get_settings().rag_chunk_size)
    )
    resolved_chunk_overlap = (
        chunk_overlap
        if chunk_overlap is not None
        else (
            getattr(runtime, "chunk_overlap", None)
            if getattr(runtime, "chunk_overlap", None) is not None
            else get_settings().rag_chunk_overlap
        )
    )
    if not 100 <= resolved_chunk_size <= 4000 or not 0 <= resolved_chunk_overlap < resolved_chunk_size:
        raise HTTPException(
            status_code=422,
            detail="chunk_size 必须为 100..4000，chunk_overlap 必须小于 chunk_size",
        )
    return runtime, resolved_chunk_size, resolved_chunk_overlap


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
    source = source.strip()
    if not source:
        raise HTTPException(status_code=422, detail="source 不能为空")
    company_id, department = _resolve_ingest_identity(
        user_id, company_id, department, authorization, uid
    )
    knowledge_base_key = knowledge_base_key.strip()
    runtime, chunk_size, chunk_overlap = _ingest_runtime(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    try:
        content = await request.body()
        if not content:
            raise ValueError("PDF 内容为空")
        if len(content) > 20 * 1024 * 1024:
            raise ValueError("PDF 大小不能超过 20MB")
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
            api_module.milvus_service.upsert_chunks,
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
    """Parse, chunk, embed and store one supported document synchronously."""
    source = source.strip()
    if not source:
        raise HTTPException(status_code=422, detail="source 不能为空，需包含文档扩展名")
    company_id, department = _resolve_ingest_identity(
        user_id, company_id, department, authorization, uid
    )
    knowledge_base_key = knowledge_base_key.strip()
    runtime, chunk_size, chunk_overlap = _ingest_runtime(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
    )
    try:
        content = await request.body()
        if len(content) > 20 * 1024 * 1024:
            raise DocumentParseError("文档大小不能超过 20MB")
        # Parsing is blocking work, but the API still waits and returns one result.
        rows, empty_pages = await run_in_threadpool(
            api_module.build_chunk_rows,
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
        # Embedding and Milvus writes are blocking network calls, so run them off
        # the event loop while keeping the endpoint's synchronous business flow.
        inserted = await run_in_threadpool(
            api_module.milvus_service.upsert_chunks,
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

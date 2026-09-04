"""RAG 检索与同步文档导入接口。"""

from __future__ import annotations

from hashlib import sha256
from io import BytesIO
from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.exc import SQLAlchemyError
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
    RagIngestJobRequest,
    RagIngestJobResponse,
    RagSearchRequest,
    RagTextIngestRequest,
)
from ai_erp_rag_assistant.app.services.document_ingest_service import (
    DocumentParseError,
    build_chunk_rows,
)
from ai_erp_rag_assistant.app.services.ingest_job_service import (
    IngestJobTracker,
    ingest_job_status,
    record_ingest_failure,
)
from ai_erp_rag_assistant.app.tools.rag_tools import search_knowledge
from ai_erp_rag_assistant.scripts.ingest_pdf import infer_title, split_text


router = APIRouter(tags=["RAG"])


def _runtime_source_fields(
    runtime: RagRuntimeConfig,
    requested_key: str,
    *,
    department: str = "",
    access_tags: list[str] | None = None,
) -> tuple[str, list[str], list[dict[str, str]], str, list[str]]:
    """把运行时检索目标整理成前端可展示的知识库和 Collection 信息。"""
    targets = list(runtime.knowledge_bases)
    if access_tags is not None:
        visible_targets = []
        for target in targets:
            try:
                target.require_access(
                    department=department,
                    permission_tags=access_tags,
                    action="read",
                )
            except PermissionError:
                continue
            visible_targets.append(target)
        targets = visible_targets
    if not targets and requested_key:
        return requested_key, [requested_key], [], runtime.collection, [runtime.collection]
    keys = [target.knowledge_base_key for target in targets]
    collections = [target.collection for target in targets]
    names = [
        {
            "knowledge_base_key": target.knowledge_base_key,
            "knowledge_base_name": target.knowledge_base_name or target.knowledge_base_key,
        }
        for target in targets
    ]
    single_key = keys[0] if len(keys) == 1 else ""
    single_collection = runtime.collection or (collections[0] if len(collections) == 1 else "")
    return single_key, keys, names, single_collection, collections


def _start_ingest_tracker(
    db: Session | None,
    *,
    company_id: str,
    knowledge_base_key: str,
    source: str,
    title: str,
    mime_type: str,
    content: bytes,
    created_by: str,
    parser: str,
    metadata: dict[str, Any],
) -> IngestJobTracker | None:
    """MySQL 与明确知识库同时可用时，创建可追踪、可重试的导入任务。"""
    if db is None or not knowledge_base_key:
        return None
    try:
        return IngestJobTracker.start(
            db,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            source=source,
            title=title,
            mime_type=mime_type,
            content=content,
            created_by=created_by,
            parser=parser,
            metadata=metadata,
        )
    except (ValueError, RuntimeError, SQLAlchemyError) as exc:
        if db is not None:
            db.rollback()
        raise HTTPException(status_code=503, detail=f"创建导入任务失败：{exc}") from exc


def _failure_detail(
    message: str, tracker: IngestJobTracker | None
) -> str | dict[str, Any]:
    """跟踪已启用时把失败任务标识返回前端，否则保持原字符串错误契约。"""
    if tracker is None:
        return message
    return {
        "message": message,
        "status": "failed",
        "retryable": True,
        **tracker.response_fields(),
    }


def _rag_rows_from_text(request: RagTextIngestRequest) -> list[dict[str, Any]]:
    """为文本导入构造带租户边界的 Chunk 行。"""
    # 在切分前完成边界参数校验，避免无效请求触发 Embedding 外部调用。
    company_id = request.company_id.strip()
    source = request.source.strip()
    # 该辅助函数也被测试和重试流程直接调用，因此在这里保留进程默认值兜底。
    chunk_size = request.chunk_size or get_settings().rag_chunk_size
    chunk_overlap = (
        request.chunk_overlap
        if request.chunk_overlap is not None
        else get_settings().rag_chunk_overlap
    )
    if not company_id:
        raise HTTPException(status_code=422, detail="company_id 不能为空")
    if not source:
        raise HTTPException(status_code=422, detail="source 不能为空")
    if chunk_overlap >= chunk_size:
        raise HTTPException(status_code=422, detail="chunk_overlap 必须小于 chunk_size")
    chunks = split_text(request.content, chunk_size, chunk_overlap)
    if not chunks:
        raise HTTPException(status_code=422, detail="content 不能只包含空白字符")
    title = request.title.strip() or source.rsplit("/", 1)[-1]
    # Chunk ID 同时包含租户、知识库和内容哈希，相同内容重试保持幂等。
    return [
        {
            "chunk_id": f"{company_id}:{request.knowledge_base_key.strip() or 'default'}:{sha256(f'{source}:{request.version}:{index}:{chunk}'.encode()).hexdigest()[:32]}",
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
    permission_tags: list[str] | None = None,
    chunk_size: int,
    chunk_overlap: int,
) -> tuple[list[dict[str, Any]], list[int]]:
    """提取 PDF 页面，同时保留页码和租户元数据。"""
    # 延迟导入便于解析测试替换 PdfReader，也避免普通接口启动时加载解析器。
    from pypdf import PdfReader

    try:
        reader = PdfReader(BytesIO(content))
    except Exception as exc:
        raise ValueError(f"PDF 文件无法读取：{exc}") from exc
    rows: list[dict[str, Any]] = []
    empty_pages: list[int] = []
    # PDF 按真实页码切分，空页单独报告，保证引用页码可以回溯原文。
    for page_number, page in enumerate(reader.pages, start=1):
        try:
            page_text = page.extract_text() or ""
        except Exception as exc:
            raise ValueError(f"PDF 第 {page_number} 页文本提取失败：{exc}") from exc
        if not page_text.strip():
            empty_pages.append(page_number)
            continue
        chunks = split_text(page_text, chunk_size, chunk_overlap)
        for chunk_number, chunk in enumerate(chunks, start=1):
            rows.append(
                {
                    "chunk_id": f"{company_id}:{knowledge_base_key or 'default'}:{sha256(f'{source}:{version}:{page_number}:{chunk_number}:{chunk}'.encode()).hexdigest()[:32]}",
                    "text": chunk,
                    "source": source,
                    "page": page_number,
                    "title": infer_title(chunk, source.rsplit("/", 1)[-1]),
                    "company_id": company_id,
                    "department": department,
                    "version": version,
                    "effective_date": effective_date,
                    "is_active": True,
                    "permission_tags": list(permission_tags or []),
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
    """按可信 ERP 身份检索知识库证据，不调用 LLM。"""
    try:
        # 身份校验同时给出可信公司、部门和 ACL 标签，不能使用请求体伪造权限。
        request, company_id, department, access_tags = api_module._rag_identity(
            request, authorization, uid
        )
        if not company_id or not request.query.strip():
            raise ValueError("company_id 和 query 不能为空")
        knowledge_base_key = request.knowledge_base_key.strip()
        runtime = api_module._rag_runtime_config(
            db,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            assistant_key=request.assistant_key.strip(),
            knowledge_base_keys=request.knowledge_base_keys,
            search_scope=request.search_scope,
        )
        # 检索参数优先使用本次 top_k，其余来自知识库运行时配置。
        evidence = search_knowledge(
            request.query,
            runtime=runtime,
            company_id=company_id,
            department=department,
            permission_tags=access_tags,
            top_k=request.top_k or runtime.top_k or 5,
            knowledge_base_key=knowledge_base_key,
        )
        (
            response_key,
            response_keys,
            searched_knowledge_bases,
            response_collection,
            response_collections,
        ) = _runtime_source_fields(
            runtime,
            knowledge_base_key,
            department=department,
            access_tags=access_tags,
        )
        return RagEvidenceResponse(
            evidence=evidence,
            citations=api_module.model_service.build_citations(evidence),
            count=len(evidence),
            company_id=company_id,
            knowledge_base_key=response_key,
            knowledge_base_keys=response_keys,
            searched_knowledge_bases=searched_knowledge_bases,
            collection=response_collection,
            collections=response_collections,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/rag/chat", response_model=RagChatResponse)
def rag_chat(
    request: RagChatRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagChatResponse:
    """检索可信知识证据并使用租户 Prompt 调用 LLM 回答。"""
    try:
        # 问答与纯检索共用相同身份和 ACL 过滤，LLM 无法绕过可见范围。
        request, company_id, department, access_tags = api_module._rag_identity(
            request, authorization, uid
        )
        if not company_id or not request.query.strip():
            raise ValueError("company_id 和 query 不能为空")
        knowledge_base_key = request.knowledge_base_key.strip()
        runtime = api_module._rag_runtime_config(
            db,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            assistant_key=request.assistant_key.strip(),
            knowledge_base_keys=request.knowledge_base_keys,
            search_scope=request.search_scope,
        )
        evidence = search_knowledge(
            request.query,
            runtime=runtime,
            company_id=company_id,
            department=department,
            permission_tags=access_tags,
            top_k=request.top_k or runtime.top_k or 5,
            knowledge_base_key=knowledge_base_key,
        )
        # 已发布平台 Prompt 在前，请求级上下文只作为附加约束参与生成。
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
        (
            response_key,
            response_keys,
            searched_knowledge_bases,
            response_collection,
            response_collections,
        ) = _runtime_source_fields(
            runtime,
            knowledge_base_key,
            department=department,
            access_tags=access_tags,
        )
        return RagChatResponse(
            message=answer,
            evidence=evidence,
            citations=api_module.model_service.build_citations(evidence),
            count=len(evidence),
            company_id=company_id,
            knowledge_base_key=response_key,
            knowledge_base_keys=response_keys,
            searched_knowledge_bases=searched_knowledge_bases,
            collection=response_collection,
            collections=response_collections,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/rag/ingest/text", response_model=RagIngestResponse)
def rag_ingest_text(
    request: RagTextIngestRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagIngestResponse:
    """同步切分文本、生成向量并写入租户知识库。"""
    # 先通过 ERP 确认公司归属，再把可信租户信息写入每个 Chunk。
    company_id, department, access_tags = _resolve_ingest_identity(
        request.user_id,
        request.company_id,
        request.department,
        authorization or request.authorization,
        uid or request.uid,
    )
    document_permission_tags = _validate_document_permission_tags(
        request.permission_tags, access_tags
    )
    request = request.model_copy(
        update={
            "company_id": company_id,
            "department": department,
            "permission_tags": document_permission_tags,
        }
    )
    knowledge_base_key = request.knowledge_base_key.strip()
    # 文本接口和 PDF/通用文档接口采用同一优先级：本次请求 > 知识库配置 > 进程默认值。
    runtime, resolved_chunk_size, resolved_chunk_overlap = _ingest_runtime(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        chunk_size=request.chunk_size,
        chunk_overlap=request.chunk_overlap,
    )
    request = request.model_copy(
        update={
            "chunk_size": resolved_chunk_size,
            "chunk_overlap": resolved_chunk_overlap,
        }
    )
    try:
        runtime.require_access(
            department=department, permission_tags=access_tags, action="write"
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    metadata = {
        "kind": "text",
        "source": request.source.strip(),
        "title": request.title.strip(),
        "company_id": company_id,
        "knowledge_base_key": knowledge_base_key,
        "department": department,
        "version": request.version,
        "effective_date": request.effective_date,
        "permission_tags": request.permission_tags,
        "chunk_size": request.chunk_size,
        "chunk_overlap": request.chunk_overlap,
    }
    tracker = _start_ingest_tracker(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        source=request.source,
        title=request.title,
        mime_type="text/plain",
        content=request.content.encode(),
        created_by=request.uid or request.user_id,
        parser="text",
        metadata=metadata,
    )
    try:
        if tracker:
            tracker.stage("parsing")
        rows = _rag_rows_from_text(request)
        if tracker:
            tracker.stage(
                "embedding", total_pages=1, parsed_pages=1, chunk_count=len(rows)
            )
        # replace_existing 仅替换同 company_id + source + version 的旧 Chunk。
        inserted = api_module.milvus_service.upsert_chunks(
            rows,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
            replace_existing=True,
        )
        if tracker:
            tracker.stage(
                "completed",
                total_pages=1,
                parsed_pages=1,
                chunk_count=len(rows),
                inserted_chunk_count=inserted,
            )
    except HTTPException as exc:
        record_ingest_failure(tracker, "parse_failed", exc)
        raise
    except ValueError as exc:
        record_ingest_failure(tracker, "ingest_validation_failed", exc)
        raise HTTPException(
            status_code=422, detail=_failure_detail(str(exc), tracker)
        ) from exc
    except (RuntimeError, SQLAlchemyError) as exc:
        record_ingest_failure(tracker, "embedding_or_milvus_failed", exc)
        raise HTTPException(
            status_code=503, detail=_failure_detail(str(exc), tracker)
        ) from exc
    return RagIngestResponse(
        source=request.source,
        chunk_count=len(rows),
        inserted_count=inserted,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        collection=runtime.collection,
        **(tracker.response_fields() if tracker else {}),
    )


def _resolve_ingest_identity(
    user_id: str,
    company_id: str,
    department: str,
    authorization: str | None,
    uid: str | None,
) -> tuple[str, str, list[str]]:
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
    requested_company = company_id.strip()
    if not resolved_company or (
        requested_company and resolved_company != requested_company
    ):
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    # 请求参数中的权限标签不参与授权，只使用 ERP 身份返回的权限和角色。
    access_tags = api_module._verified_access_tags(user)
    return (
        resolved_company,
        # ERP 未返回部门时保持为空；后续 Milvus 只允许公共文档，不能信任请求体部门。
        str(user.get("department") or "").strip(),
        access_tags,
    )


def _validate_document_permission_tags(
    requested_tags: list[str], access_tags: list[str]
) -> list[str]:
    """限制上传者只能给文档设置自己已拥有的 ACL 标签。"""
    normalized: list[str] = []
    seen: set[str] = set()
    for tag in requested_tags:
        value = str(tag).strip()
        if len(value) > 256:
            raise HTTPException(status_code=422, detail="单个 permission_tags 不能超过 256 个字符")
        if value and value not in seen:
            normalized.append(value)
            seen.add(value)
    # Milvus ARRAY 字段的容量是 32；在外部调用前拒绝超限，避免写入阶段才返回模糊错误。
    if len(normalized) > 32:
        raise HTTPException(status_code=422, detail="permission_tags 最多支持 32 个标签")
    # 文档标签会写入 Milvus 并决定后续可见范围，不能让普通用户借请求体制造更宽的授权。
    unauthorized = sorted(set(normalized) - set(access_tags))
    if unauthorized:
        raise HTTPException(
            status_code=403,
            detail="文档权限标签超出当前用户可授予范围：" + "、".join(unauthorized),
        )
    return normalized


def _ingest_runtime(
    db: Session | None,
    *,
    company_id: str,
    knowledge_base_key: str,
    chunk_size: int | None,
    chunk_overlap: int | None,
) -> tuple[RagRuntimeConfig, int, int]:
    """合并知识库与单次请求的切分参数，并验证最终组合。"""
    if db is not None and not knowledge_base_key.strip():
        # 公司级自动检索可以不选库；导入必须明确归属，避免文件落到错误的 Collection。
        raise HTTPException(status_code=422, detail="导入文件必须指定 knowledge_base_key")
    # 单次 Query 参数优先，其次知识库配置，最后回退到进程默认值。
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
    # 校验最终生效值而不只是请求参数，数据库旧配置同样不能绕过边界。
    if not 100 <= resolved_chunk_size <= 4000 or not 0 <= resolved_chunk_overlap < resolved_chunk_size:
        raise HTTPException(
            status_code=422,
            detail="chunk_size 必须为 100..4000，chunk_overlap 必须小于 chunk_size",
        )
    return runtime, resolved_chunk_size, resolved_chunk_overlap


@router.post("/rag/ingest/pdf", response_model=RagIngestResponse)
async def rag_ingest_pdf(
    request: Request,
    company_id: str = "",
    user_id: str = "",
    source: str = "uploaded.pdf",
    knowledge_base_key: str = "",
    department: str = "",
    version: str = "",
    effective_date: str = "",
    permission_tags: str = "",
    chunk_size: int | None = None,
    chunk_overlap: int | None = None,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagIngestResponse:
    """同步导入一个以 application/pdf 请求体提交的 PDF 文件。"""
    # 专用 PDF 接口严格校验媒体类型，通用格式请走 /rag/ingest/document。
    content_type = (request.headers.get("content-type") or "").split(";", 1)[0].lower()
    if content_type != "application/pdf":
        raise HTTPException(status_code=415, detail="PDF 导入必须使用 Content-Type: application/pdf")
    source = source.strip()
    if not source:
        raise HTTPException(status_code=422, detail="source 不能为空")
    company_id, department, access_tags = _resolve_ingest_identity(
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
        runtime.require_access(
            department=department, permission_tags=access_tags, action="write"
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    # 专用 PDF 接口与通用文档接口共用同一 ACL 规则，不能通过旧入口绕过标签校验。
    document_permission_tags = _validate_document_permission_tags(
        permission_tags.split(","), access_tags
    )
    # 空请求和超大请求在创建任务前拒绝，避免保存没有重试价值的载荷。
    content = await request.body()
    if not content:
        raise HTTPException(status_code=422, detail="PDF 内容为空")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="PDF 大小不能超过 20MB")
    metadata = {
        "kind": "pdf",
        "source": source,
        "title": "",
        "company_id": company_id,
        "knowledge_base_key": knowledge_base_key,
        "department": department,
        "version": version,
        "effective_date": effective_date,
        "permission_tags": document_permission_tags,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
    }
    tracker = _start_ingest_tracker(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        source=source,
        title="",
        mime_type="application/pdf",
        content=content,
        created_by=uid or user_id,
        parser="pdf",
        metadata=metadata,
    )
    try:
        if tracker:
            tracker.stage("parsing")
        # PDF 解析为阻塞 CPU/文件操作，在线程池中运行但请求仍同步等待。
        rows, empty_pages = await run_in_threadpool(
            _rag_rows_from_pdf,
            content,
            company_id=company_id,
            source=source,
            knowledge_base_key=knowledge_base_key,
            department=department,
            version=version,
            effective_date=effective_date,
            permission_tags=document_permission_tags,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if not rows:
            raise ValueError("PDF 没有可提取文本；扫描件请先生成文字层")
        if tracker:
            tracker.stage(
                "embedding",
                total_pages=len({row["page"] for row in rows}) + len(empty_pages),
                parsed_pages=len({row["page"] for row in rows}),
                chunk_count=len(rows),
            )
        # Embedding 和 Milvus 都是阻塞网络调用，移出事件循环但仍保持同步业务语义。
        inserted = await run_in_threadpool(
            api_module.milvus_service.upsert_chunks,
            rows,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
            replace_existing=True,
        )
        if tracker:
            tracker.stage(
                "completed",
                total_pages=len({row["page"] for row in rows}) + len(empty_pages),
                parsed_pages=len({row["page"] for row in rows}),
                chunk_count=len(rows),
                inserted_chunk_count=inserted,
            )
    except ValueError as exc:
        record_ingest_failure(tracker, "pdf_parse_failed", exc)
        raise HTTPException(
            status_code=422,
            detail=_failure_detail(f"PDF 解析失败：{exc}", tracker),
        ) from exc
    except (RuntimeError, SQLAlchemyError) as exc:
        record_ingest_failure(tracker, "embedding_or_milvus_failed", exc)
        raise HTTPException(
            status_code=503, detail=_failure_detail(str(exc), tracker)
        ) from exc
    return RagIngestResponse(
        source=source,
        chunk_count=len(rows),
        inserted_count=inserted,
        empty_pages=empty_pages,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        collection=runtime.collection,
        **(tracker.response_fields() if tracker else {}),
    )


@router.post("/rag/ingest/document", response_model=RagIngestResponse)
async def rag_ingest_document(
    request: Request,
    source: str,
    company_id: str = "",
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
    """同步解析、切分、向量化并保存一个受支持的文档。"""
    # source 扩展名决定解析器，因此在读取大文件前先拒绝空来源。
    source = source.strip()
    if not source:
        raise HTTPException(status_code=422, detail="source 不能为空，需包含文档扩展名")
    company_id, department, access_tags = _resolve_ingest_identity(
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
        runtime.require_access(
            department=department, permission_tags=access_tags, action="write"
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    content = await request.body()
    if not content:
        raise HTTPException(status_code=422, detail="文档内容为空")
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=422, detail="文档大小不能超过 20MB")
    document_permission_tags = _validate_document_permission_tags(
        permission_tags.split(","), access_tags
    )
    metadata = {
        "kind": "document",
        "source": source,
        "title": title,
        "company_id": company_id,
        "knowledge_base_key": knowledge_base_key,
        "department": department,
        "version": version,
        "effective_date": effective_date,
        "permission_tags": document_permission_tags,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
    }
    content_type = (request.headers.get("content-type") or "application/octet-stream").split(";", 1)[0]
    tracker = _start_ingest_tracker(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        source=source,
        title=title,
        mime_type=content_type[:127],
        content=content,
        created_by=uid or user_id,
        parser="document",
        metadata=metadata,
    )
    try:
        if tracker:
            tracker.stage("parsing")
        # 解析属于阻塞操作，但接口仍等待整条流水线完成后一次性返回结果。
        rows, empty_pages = await run_in_threadpool(
            api_module.build_chunk_rows,
            content,
            company_id=company_id,
            source=source,
            knowledge_base_key=knowledge_base_key,
            department=department,
            version=version,
            effective_date=effective_date,
            permission_tags=document_permission_tags,
            title=title,
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
        )
        if tracker:
            pages = {int(row.get("page") or 0) for row in rows if row.get("page")}
            tracker.stage(
                "embedding",
                total_pages=len(pages) + len(empty_pages),
                parsed_pages=len(pages),
                chunk_count=len(rows),
            )
        # Embedding 和 Milvus 写入属于阻塞网络调用，移出事件循环但保持同步业务语义。
        inserted = await run_in_threadpool(
            api_module.milvus_service.upsert_chunks,
            rows,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
            replace_existing=True,
        )
        if tracker:
            tracker.stage(
                "completed",
                total_pages=len(pages) + len(empty_pages),
                parsed_pages=len(pages),
                chunk_count=len(rows),
                inserted_chunk_count=inserted,
            )
    except DocumentParseError as exc:
        record_ingest_failure(tracker, "document_parse_failed", exc)
        raise HTTPException(
            status_code=422, detail=_failure_detail(str(exc), tracker)
        ) from exc
    except ValueError as exc:
        record_ingest_failure(tracker, "ingest_validation_failed", exc)
        raise HTTPException(
            status_code=422, detail=_failure_detail(str(exc), tracker)
        ) from exc
    except (RuntimeError, SQLAlchemyError) as exc:
        record_ingest_failure(tracker, "embedding_or_milvus_failed", exc)
        raise HTTPException(
            status_code=503, detail=_failure_detail(str(exc), tracker)
        ) from exc
    return RagIngestResponse(
        source=source,
        chunk_count=len(rows),
        inserted_count=inserted,
        empty_pages=empty_pages,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        collection=runtime.collection,
        **(tracker.response_fields() if tracker else {}),
    )


@router.post("/rag/ingest/jobs/status", response_model=RagIngestJobResponse)
def rag_ingest_job_status(
    request: RagIngestJobRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagIngestJobResponse:
    """查询同步导入的当前阶段、计数和失败原因。"""
    company_id, department, access_tags = _resolve_ingest_identity(
        request.user_id,
        request.company_id,
        request.department,
        authorization or request.authorization,
        uid or request.uid,
    )
    if db is None:
        raise HTTPException(status_code=503, detail="未配置 MySQL，无法查询导入任务")
    knowledge_base_key = request.knowledge_base_key.strip()
    runtime = api_module._rag_runtime_config(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        assistant_key="",
    )
    try:
        runtime.require_access(
            department=department, permission_tags=access_tags, action="write"
        )
        item = ingest_job_status(db, company_id=company_id, job_id=request.job_id)
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="MySQL 查询导入任务失败") from exc
    # 请求知识库与任务必须一致，避免用一个有权限的知识库探测同公司其他任务。
    if item["knowledge_base_key"] != knowledge_base_key:
        raise HTTPException(status_code=404, detail="导入任务不存在")
    return RagIngestJobResponse.model_validate(item)


@router.post("/rag/ingest/jobs/retry", response_model=RagIngestResponse)
async def rag_retry_ingest_job(
    request: RagIngestJobRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagIngestResponse:
    """使用服务端留存源文件重跑失败任务，并创建新的审计任务记录。"""
    company_id, department, access_tags = _resolve_ingest_identity(
        request.user_id,
        request.company_id,
        request.department,
        authorization or request.authorization,
        uid or request.uid,
    )
    if db is None:
        raise HTTPException(status_code=503, detail="未配置 MySQL，无法重试导入任务")
    knowledge_base_key = request.knowledge_base_key.strip()
    runtime, _, _ = _ingest_runtime(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        chunk_size=None,
        chunk_overlap=None,
    )
    try:
        runtime.require_access(
            department=department, permission_tags=access_tags, action="write"
        )

        def prepare_retry_metadata(metadata: dict[str, Any]) -> None:
            """在创建新补偿任务前重新确认历史文档 ACL。"""
            stored_tags = metadata.get("permission_tags") or []
            if isinstance(stored_tags, str):
                stored_tags = stored_tags.split(",")
            metadata["permission_tags"] = _validate_document_permission_tags(
                list(stored_tags), access_tags
            )

        tracker, content, metadata, _ = IngestJobTracker.retry(
            db,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            failed_job_id=request.job_id,
            prepare_metadata=prepare_retry_metadata,
        )
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (RuntimeError, SQLAlchemyError) as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    source = str(metadata.get("source") or "").strip()
    chunk_size = int(metadata.get("chunk_size") or get_settings().rag_chunk_size)
    chunk_overlap = int(metadata.get("chunk_overlap") or get_settings().rag_chunk_overlap)
    empty_pages: list[int] = []
    try:
        tracker.stage("parsing")
        kind = str(metadata.get("kind") or "")
        if kind == "text":
            rows = _rag_rows_from_text(
                RagTextIngestRequest(
                    content=content.decode("utf-8"),
                    company_id=company_id,
                    source=source,
                    title=str(metadata.get("title") or ""),
                    knowledge_base_key=knowledge_base_key,
                    department=str(metadata.get("department") or department),
                    version=str(metadata.get("version") or ""),
                    effective_date=str(metadata.get("effective_date") or ""),
                    permission_tags=list(metadata.get("permission_tags") or []),
                    chunk_size=chunk_size,
                    chunk_overlap=chunk_overlap,
                )
            )
        elif kind == "pdf":
            rows, empty_pages = await run_in_threadpool(
                _rag_rows_from_pdf,
                content,
                company_id=company_id,
                source=source,
                knowledge_base_key=knowledge_base_key,
                department=str(metadata.get("department") or department),
                version=str(metadata.get("version") or ""),
                effective_date=str(metadata.get("effective_date") or ""),
                permission_tags=list(metadata.get("permission_tags") or []),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        elif kind == "document":
            rows, empty_pages = await run_in_threadpool(
                build_chunk_rows,
                content,
                company_id=company_id,
                source=source,
                knowledge_base_key=knowledge_base_key,
                department=str(metadata.get("department") or department),
                version=str(metadata.get("version") or ""),
                effective_date=str(metadata.get("effective_date") or ""),
                permission_tags=list(metadata.get("permission_tags") or []),
                title=str(metadata.get("title") or ""),
                chunk_size=chunk_size,
                chunk_overlap=chunk_overlap,
            )
        else:
            raise ValueError("导入任务的 parser 类型无法识别")
        pages = {int(row.get("page") or 0) for row in rows if row.get("page")}
        tracker.stage(
            "embedding",
            total_pages=len(pages) + len(empty_pages),
            parsed_pages=len(pages),
            chunk_count=len(rows),
        )
        inserted = await run_in_threadpool(
            api_module.milvus_service.upsert_chunks,
            rows,
            company_id=company_id,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
            replace_existing=True,
        )
        tracker.stage(
            "completed",
            total_pages=len(pages) + len(empty_pages),
            parsed_pages=len(pages),
            chunk_count=len(rows),
            inserted_chunk_count=inserted,
        )
    except (DocumentParseError, UnicodeError, ValueError) as exc:
        record_ingest_failure(tracker, "retry_parse_failed", exc)
        raise HTTPException(
            status_code=422, detail=_failure_detail(str(exc), tracker)
        ) from exc
    except (RuntimeError, SQLAlchemyError) as exc:
        record_ingest_failure(tracker, "retry_write_failed", exc)
        raise HTTPException(
            status_code=503, detail=_failure_detail(str(exc), tracker)
        ) from exc
    return RagIngestResponse(
        source=source,
        chunk_count=len(rows),
        inserted_count=inserted,
        empty_pages=empty_pages,
        company_id=company_id,
        knowledge_base_key=knowledge_base_key,
        collection=runtime.collection,
        **tracker.response_fields(),
    )

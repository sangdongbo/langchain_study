"""RAG 同步导入流水线，统一解析、切分、向量写入和任务阶段。"""

from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
from typing import Any

from starlette.concurrency import run_in_threadpool

from ai_erp_rag_assistant.app.services.document_ingest_service import build_chunk_rows
from ai_erp_rag_assistant.app.services.ingest_job_service import IngestJobTracker
from ai_erp_rag_assistant.app.services.milvus_service import milvus_service
from ai_erp_rag_assistant.scripts.ingest_pdf import split_text


@dataclass(frozen=True)
class IngestPipelineResult:
    """一次同步导入完成后的稳定统计。"""

    chunk_count: int
    inserted_count: int
    empty_pages: list[int]


def build_text_chunk_rows(
    content: str,
    *,
    company_id: str,
    source: str,
    knowledge_base_key: str = "",
    department: str = "",
    version: str = "",
    effective_date: str = "",
    permission_tags: list[str] | None = None,
    title: str = "",
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> list[dict[str, Any]]:
    """将文本请求切分为带租户和知识库边界的 Chunk。"""
    company_id = company_id.strip()
    source = source.strip()
    if not company_id:
        raise ValueError("company_id 不能为空")
    if not source:
        raise ValueError("source 不能为空")
    if not 100 <= chunk_size <= 4000:
        raise ValueError("chunk_size 必须为 100..4000")
    if not 0 <= chunk_overlap < chunk_size:
        raise ValueError("chunk_overlap 必须小于 chunk_size")
    chunks = split_text(content, chunk_size, chunk_overlap)
    if not chunks:
        raise ValueError("content 不能只包含空白字符")

    knowledge_key = knowledge_base_key.strip() or "default"
    resolved_title = title.strip() or source.rsplit("/", 1)[-1]
    tags = list(permission_tags or [])
    rows: list[dict[str, Any]] = []
    for index, chunk in enumerate(chunks, start=1):
        # 内容参与哈希，相同文本重试保持 Chunk ID 稳定。
        digest = sha256(
            f"{source}:{version}:{index}:{chunk}".encode()
        ).hexdigest()[:32]
        rows.append(
            {
                "chunk_id": f"{company_id}:{knowledge_key}:{digest}",
                "text": chunk,
                "source": source,
                "page": 1,
                "title": resolved_title,
                "company_id": company_id,
                "department": department,
                "version": version,
                "effective_date": effective_date,
                "is_active": True,
                "permission_tags": tags,
            }
        )
    return rows


async def run_ingest_pipeline(
    content: bytes,
    *,
    metadata: dict[str, Any],
    collection_name: str,
    tracker: IngestJobTracker | None = None,
) -> IngestPipelineResult:
    """等待完整导入结果，仅把阻塞解析和外部调用放入工作线程。"""
    kind = str(metadata.get("kind") or "").strip()
    common = {
        "company_id": str(metadata.get("company_id") or ""),
        "source": str(metadata.get("source") or ""),
        "knowledge_base_key": str(metadata.get("knowledge_base_key") or ""),
        "department": str(metadata.get("department") or ""),
        "version": str(metadata.get("version") or ""),
        "effective_date": str(metadata.get("effective_date") or ""),
        "permission_tags": list(metadata.get("permission_tags") or []),
        "title": str(metadata.get("title") or ""),
        "chunk_size": int(metadata.get("chunk_size") or 0),
        "chunk_overlap": int(metadata.get("chunk_overlap") or 0),
    }
    if tracker:
        tracker.stage("parsing")

    if kind == "text":
        rows = await run_in_threadpool(
            build_text_chunk_rows,
            content.decode("utf-8"),
            **common,
        )
        empty_pages: list[int] = []
    elif kind in {"pdf", "document"}:
        rows, empty_pages = await run_in_threadpool(
            build_chunk_rows,
            content,
            **common,
        )
    else:
        raise ValueError("导入任务的 parser 类型无法识别")

    pages = {int(row.get("page") or 0) for row in rows if row.get("page")}
    total_pages = len(pages) + len(empty_pages)
    parsed_pages = len(pages)
    if tracker:
        tracker.stage(
            "embedding",
            total_pages=total_pages,
            parsed_pages=parsed_pages,
            chunk_count=len(rows),
        )

    # MilvusService 在内部完成 Embedding 和 Collection 维度校验。
    inserted = await run_in_threadpool(
        milvus_service.upsert_chunks,
        rows,
        company_id=common["company_id"],
        knowledge_base_key=common["knowledge_base_key"],
        collection_name=collection_name,
        replace_existing=True,
    )
    if tracker:
        tracker.stage(
            "completed",
            total_pages=total_pages,
            parsed_pages=parsed_pages,
            chunk_count=len(rows),
            inserted_chunk_count=inserted,
        )
    return IngestPipelineResult(
        chunk_count=len(rows),
        inserted_count=inserted,
        empty_pages=empty_pages,
    )

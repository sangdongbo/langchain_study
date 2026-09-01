"""保存同步导入源文件，并把各处理阶段写入已有 MySQL 任务表。"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable
from dataclasses import dataclass
from hashlib import sha256
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlalchemy.orm import Session

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.rag_admin_repository import (
    RagAdminRepository,
    row_dict,
)


logger = logging.getLogger("ai_erp_rag_assistant.ingest")


@dataclass
class IngestJobTracker:
    """一个同步导入请求对应的持久化任务句柄。"""

    session: Session
    company_id: str
    job_id: int
    job_key: str
    document_id: int
    knowledge_base_id: int
    storage_uri: str

    @classmethod
    def start(
        cls,
        session: Session,
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
    ) -> "IngestJobTracker":
        """先创建数据库任务，再保存重试所需的源文件与非敏感参数。"""
        job_key = uuid4().hex
        job_dir = _job_root(company_id) / job_key
        suffix = Path(source).suffix.lower()
        source_path = job_dir / f"source{suffix if suffix and len(suffix) <= 12 else '.bin'}"
        repository = RagAdminRepository(session)
        job, document, knowledge_base = repository.create_ingest_job(
            company_id,
            knowledge_base_key,
            job_key=job_key,
            source=source,
            title=title,
            mime_type=mime_type,
            storage_uri=str(source_path),
            content_sha256=sha256(content).hexdigest(),
            created_by=created_by,
            permission_scope={
                "department": metadata.get("department") or "",
                "permission_tags": metadata.get("permission_tags") or [],
            },
            parser=parser,
            embedding_model=get_settings().embedding_model,
        )
        tracker = cls(
            session=session,
            company_id=company_id,
            job_id=job.id,
            job_key=job.job_key,
            document_id=document.id,
            knowledge_base_id=knowledge_base.id,
            storage_uri=str(source_path),
        )
        try:
            # Sidecar 只保存重建切分所需的业务参数，不写认证头或任何服务凭据。
            job_dir.mkdir(parents=True, exist_ok=True)
            source_path.write_bytes(content)
            (job_dir / "request.json").write_text(
                json.dumps(metadata, ensure_ascii=False, sort_keys=True),
                encoding="utf-8",
            )
        except OSError as exc:
            tracker.fail("source_storage_failed", str(exc))
            raise RuntimeError(f"导入源文件保存失败：{exc}") from exc
        return tracker

    @classmethod
    def retry(
        cls,
        session: Session,
        *,
        company_id: str,
        knowledge_base_key: str,
        failed_job_id: int,
        prepare_metadata: Callable[[dict[str, Any]], None] | None = None,
    ) -> tuple["IngestJobTracker", bytes, dict[str, Any], str]:
        """读取源文件并创建补偿任务；元数据预校验在改写数据库状态前执行。"""
        repository = RagAdminRepository(session)
        failed_job, document, knowledge_base = repository.get_ingest_job(
            company_id, failed_job_id
        )
        if failed_job.status != "failed":
            raise ValueError("只有 failed 状态的导入任务可以重试")
        if document.status != "failed":
            raise ValueError("该文档已有其他任务处理中或已完成，不能重复补偿")
        if knowledge_base.knowledge_key != knowledge_base_key.strip():
            raise ValueError("导入任务不属于请求中的知识库")
        source_path = _validated_storage_path(document.storage_uri or "", company_id)
        sidecar_path = source_path.parent / "request.json"
        try:
            content = source_path.read_bytes()
            metadata = json.loads(sidecar_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise RuntimeError(f"导入补偿源文件不可用：{exc}") from exc
        if not isinstance(metadata, dict):
            raise RuntimeError("导入补偿元数据格式无效")
        # ACL、业务字段等调用方校验必须在 create_ingest_retry 前完成；失败时不能留下 pending 任务。
        if prepare_metadata is not None:
            prepare_metadata(metadata)
        job, _, _ = repository.create_ingest_retry(
            company_id, failed_job_id, job_key=uuid4().hex
        )
        return (
            cls(
                session=session,
                company_id=company_id,
                job_id=job.id,
                job_key=job.job_key,
                document_id=document.id,
                knowledge_base_id=knowledge_base.id,
                storage_uri=str(source_path),
            ),
            content,
            metadata,
            knowledge_base.knowledge_key,
        )

    def stage(self, status: str, **values: Any) -> None:
        """推进任务阶段；Repository 同步维护对应文档状态。"""
        RagAdminRepository(self.session).update_ingest_job(
            self.company_id, self.job_id, status=status, **values
        )

    def fail(self, error_code: str, message: str) -> None:
        """记录可展示但已截断的错误，避免完整外部响应进入数据库。"""
        RagAdminRepository(self.session).update_ingest_job(
            self.company_id,
            self.job_id,
            status="failed",
            error_code=error_code[:64],
            error_message=message,
        )

    def response_fields(self) -> dict[str, Any]:
        return {"job_id": self.job_id, "job_key": self.job_key}


def ingest_job_status(
    session: Session, *, company_id: str, job_id: int
) -> dict[str, Any]:
    """返回租户范围内任务及文档状态，不暴露本地 storage_uri。"""
    job, document, knowledge_base = RagAdminRepository(session).get_ingest_job(
        company_id, job_id
    )
    job_data = row_dict(job)
    return {
        **job_data,
        "document_status": document.status,
        "source": document.file_name or "",
        "knowledge_base_key": knowledge_base.knowledge_key,
        "retryable": (
            job.status == "failed"
            and document.status == "failed"
            and bool(document.storage_uri)
        ),
    }


def record_ingest_failure(
    tracker: IngestJobTracker | None, error_code: str, error: Exception
) -> None:
    """失败状态写入不能覆盖原始解析或外部服务异常。"""
    if tracker is None:
        return
    try:
        tracker.fail(error_code, str(error))
    except Exception as tracking_error:
        logger.exception(
            "Failed to persist ingest failure for job %s: %s",
            tracker.job_id,
            tracking_error,
        )


def _job_root(company_id: str) -> Path:
    tenant = sha256(company_id.strip().encode()).hexdigest()[:16]
    return (get_settings().rag_processed_dir / "ingest_jobs" / tenant).resolve()


def _validated_storage_path(storage_uri: str, company_id: str) -> Path:
    """拒绝数据库中被篡改为任务目录之外的本地路径。"""
    path = Path(storage_uri).resolve()
    root = _job_root(company_id)
    if path == root or root not in path.parents:
        raise RuntimeError("导入补偿文件路径超出当前租户任务目录")
    return path

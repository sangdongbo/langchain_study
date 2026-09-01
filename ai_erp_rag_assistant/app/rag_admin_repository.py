"""RAG 管理数据仓储，统一实施 company_id 隔离和版本发布事务。"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from sqlalchemy import func, inspect, select, update
from sqlalchemy.orm import Session

from ai_erp_rag_assistant.app.models import (
    Assistant,
    AssistantConfigVersion,
    AssistantKnowledgeBase,
    DataSource,
    KnowledgeBase,
    KnowledgeBaseSource,
    KnowledgeDocument,
    KnowledgeIngestJob,
    PromptVersion,
)


class AdminNotFoundError(LookupError):
    """租户范围内未找到管理对象时抛出的业务异常。"""

    pass


@dataclass(frozen=True)
class RagRuntimeConfig:
    """从知识库、Assistant 配置、绑定和 Prompt 合并出的运行时参数。"""

    collection: str
    system_context: str = ""
    # 已发布 Assistant 配置与知识问答 Prompt 合并后的安全模型参数。
    model_overrides: dict[str, Any] | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    top_k: int | None = None
    score_threshold: float | None = None
    rerank_enabled: bool | None = None
    rerank_candidates: int | None = None
    # 知识库策略和 Assistant 绑定策略分别校验，任一策略都只能收窄权限。
    permission_policies: tuple[dict[str, Any], ...] = ()

    def require_access(
        self,
        *,
        department: str,
        permission_tags: list[str],
        action: str = "read",
    ) -> None:
        """校验运行时知识库策略；身份标签必须来自已经验证的 ERP 用户。"""
        user_tags = {str(tag).strip() for tag in permission_tags if str(tag).strip()}
        department = department.strip()
        for policy in self.permission_policies:
            allowed_departments = _policy_values(policy, "allowed_departments")
            if allowed_departments and department not in allowed_departments:
                raise PermissionError("当前部门无权访问该知识库")
            # required_tags 是所有动作的基础门禁，动作级标签用于区分查询、导入和删除。
            required_tags = {
                *_policy_values(policy, "required_tags"),
                *_policy_values(policy, f"{action}_required_tags"),
            }
            if not required_tags.issubset(user_tags):
                raise PermissionError("当前用户缺少知识库所需权限")
            any_tags = _policy_values(policy, "any_tags")
            if any_tags and user_tags.isdisjoint(any_tags):
                raise PermissionError("当前用户不在知识库允许的权限范围内")


def row_dict(row: Any) -> dict[str, Any]:
    """将已加载 ORM 列转成接口可序列化字典，不触发延迟加载。"""
    state = inspect(row)
    return {
        attribute.key: None if attribute.key in state.unloaded else getattr(row, attribute.key)
        for attribute in state.mapper.column_attrs
        if attribute.key != "published_slot"
    }


def _content_hash(value: Any) -> str:
    """对排序后的规范 JSON 计算稳定哈希，用于版本内容标识。"""
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode()).hexdigest()


def _policy_values(policy: dict[str, Any], key: str) -> set[str]:
    """把管理员配置的单值或数组权限字段规范成非空字符串集合。"""
    raw = policy.get(key) or []
    values = [raw] if isinstance(raw, str) else raw
    if not isinstance(values, (list, tuple, set)):
        return set()
    return {str(value).strip() for value in values if str(value).strip()}


class RagAdminRepository:
    """封装 RAG 管理对象的租户查询、保存、绑定和发布操作。"""

    def __init__(self, session: Session):
        self.session = session

    @staticmethod
    def _company(company_id: str) -> str:
        company_id = company_id.strip()
        if not company_id:
            raise ValueError("company_id 不能为空")
        return company_id

    def _save(self, row: Any) -> Any:
        self.session.add(row)
        self.session.commit()
        return row

    def get_assistant(self, company_id: str, assistant_id: int) -> Assistant:
        """按公司和主键读取未删除的 Assistant。"""
        row = self.session.scalar(
            select(Assistant).where(
                Assistant.company_id == self._company(company_id),
                Assistant.id == assistant_id,
                Assistant.deleted_at.is_(None),
            )
        )
        if row is None:
            raise AdminNotFoundError("Assistant 不存在")
        return row

    def get_assistant_by_key(self, company_id: str, assistant_key: str) -> Assistant:
        """按公司和稳定业务标识读取未删除的 Assistant。"""
        row = self.session.scalar(
            select(Assistant).where(
                Assistant.company_id == self._company(company_id),
                Assistant.assistant_key == assistant_key,
                Assistant.deleted_at.is_(None),
            )
        )
        if row is None:
            raise AdminNotFoundError("Assistant 不存在")
        return row

    def create_assistant(self, company_id: str, assistant_key: str, name: str, created_by: str) -> Assistant:
        """在指定公司内创建 Assistant。"""
        return self._save(
            Assistant(
                company_id=self._company(company_id),
                assistant_key=assistant_key,
                name=name,
                created_by=created_by or None,
            )
        )

    def list_assistants(self, company_id: str, status: str | None = None) -> list[Assistant]:
        """按公司列出未删除的 Assistant，可选状态过滤。"""
        statement = select(Assistant).where(
            Assistant.company_id == self._company(company_id), Assistant.deleted_at.is_(None)
        )
        if status:
            statement = statement.where(Assistant.status == status)
        return list(self.session.scalars(statement.order_by(Assistant.id.desc())).all())

    def update_assistant(
        self, company_id: str, assistant_id: int, values: dict[str, Any]
    ) -> Assistant:
        """在指定公司内更新 Assistant，避免跨租户使用相同 ID 修改数据。"""
        row = self.get_assistant(company_id, assistant_id)
        for key, value in values.items():
            setattr(row, key, value)
        return self._save(row)

    def create_config_version(
        self,
        company_id: str,
        assistant_id: int,
        config: dict[str, Any],
        created_by: str,
    ) -> AssistantConfigVersion:
        """为 Assistant 生成递增配置版本并保存为草稿。"""
        company_id = self._company(company_id)
        self.get_assistant(company_id, assistant_id)
        # 版本号只在同一 company_id + assistant_id 范围内递增。
        version = int(
            self.session.scalar(
                select(func.coalesce(func.max(AssistantConfigVersion.version), 0)).where(
                    AssistantConfigVersion.company_id == company_id,
                    AssistantConfigVersion.assistant_id == assistant_id,
                )
            )
            or 0
        ) + 1
        # 配置内容使用规范 JSON 哈希，便于审计相同参数生成的不同版本。
        return self._save(
            AssistantConfigVersion(
                company_id=company_id,
                assistant_id=assistant_id,
                version=version,
                page_config_json=config["page_config"] or None,
                model_config_json=config["model_config"] or None,
                retrieval_config_json=config["retrieval_config"] or None,
                feature_flags_json=config["feature_flags"] or None,
                config_hash=_content_hash(config),
                created_by=created_by or None,
            )
        )

    def list_config_versions(self, company_id: str, assistant_id: int) -> list[AssistantConfigVersion]:
        """按版本倒序列出一个 Assistant 的全部配置。"""
        company_id = self._company(company_id)
        self.get_assistant(company_id, assistant_id)
        return list(
            self.session.scalars(
                select(AssistantConfigVersion)
                .where(
                    AssistantConfigVersion.company_id == company_id,
                    AssistantConfigVersion.assistant_id == assistant_id,
                )
                .order_by(AssistantConfigVersion.version.desc())
            ).all()
        )

    def publish_config(
        self, company_id: str, assistant_id: int, config_id: int, published_by: str
    ) -> AssistantConfigVersion:
        """原子归档旧发布配置并切换 Assistant 的发布版本指针。"""
        company_id = self._company(company_id)
        assistant = self.get_assistant(company_id, assistant_id)
        target = self.session.scalar(
            select(AssistantConfigVersion).where(
                AssistantConfigVersion.company_id == company_id,
                AssistantConfigVersion.assistant_id == assistant_id,
                AssistantConfigVersion.id == config_id,
            )
        )
        if target is None:
            raise AdminNotFoundError("配置版本不存在")
        # 重复发布当前版本直接返回，避免无意义归档和时间戳变化。
        if target.status == "published":
            return target
        now = datetime.now(UTC).replace(tzinfo=None)
        # 归档旧版本和发布目标版本必须同事务提交，避免运行时读到发布空档。
        self.session.execute(
            update(AssistantConfigVersion)
            .where(
                AssistantConfigVersion.company_id == company_id,
                AssistantConfigVersion.assistant_id == assistant_id,
                AssistantConfigVersion.status == "published",
            )
            .values(status="archived", archived_at=now)
        )
        target.status = "published"
        target.published_by = published_by or None
        target.published_at = now
        assistant.published_config_version_id = target.id
        self.session.commit()
        return target

    def create_prompt_version(
        self,
        company_id: str,
        assistant_id: int,
        prompt_key: str,
        variant: str,
        content: str,
        model_overrides: dict[str, Any],
        created_by: str,
    ) -> PromptVersion:
        """为指定 Prompt 用途和变体生成递增草稿版本。"""
        company_id = self._company(company_id)
        self.get_assistant(company_id, assistant_id)
        # 不同 prompt_key/variant 各自维护独立版本序列。
        version = int(
            self.session.scalar(
                select(func.coalesce(func.max(PromptVersion.version), 0)).where(
                    PromptVersion.company_id == company_id,
                    PromptVersion.assistant_id == assistant_id,
                    PromptVersion.prompt_key == prompt_key,
                    PromptVersion.variant == variant,
                )
            )
            or 0
        ) + 1
        # Prompt 文本单独计算哈希，模型覆盖参数仍随版本记录保存。
        return self._save(
            PromptVersion(
                company_id=company_id,
                assistant_id=assistant_id,
                prompt_key=prompt_key,
                variant=variant,
                version=version,
                content=content,
                content_hash=sha256(content.encode()).hexdigest(),
                model_overrides_json=model_overrides or None,
                created_by=created_by or None,
            )
        )

    def list_prompt_versions(
        self,
        company_id: str,
        assistant_id: int,
        prompt_key: str = "",
        variant: str | None = None,
    ) -> list[PromptVersion]:
        """列出 Assistant 的 Prompt 版本，可按用途和变体过滤。"""
        company_id = self._company(company_id)
        self.get_assistant(company_id, assistant_id)
        statement = select(PromptVersion).where(
            PromptVersion.company_id == company_id, PromptVersion.assistant_id == assistant_id
        )
        if prompt_key:
            statement = statement.where(PromptVersion.prompt_key == prompt_key)
        if variant:
            statement = statement.where(PromptVersion.variant == variant)
        return list(
            self.session.scalars(
                statement.order_by(PromptVersion.prompt_key, PromptVersion.variant, PromptVersion.version.desc())
            ).all()
        )

    def publish_prompt(
        self, company_id: str, assistant_id: int, prompt_id: int, published_by: str
    ) -> PromptVersion:
        """原子归档同用途旧 Prompt 并发布目标版本。"""
        company_id = self._company(company_id)
        self.get_assistant(company_id, assistant_id)
        target = self.session.scalar(
            select(PromptVersion).where(
                PromptVersion.company_id == company_id,
                PromptVersion.assistant_id == assistant_id,
                PromptVersion.id == prompt_id,
            )
        )
        if target is None:
            raise AdminNotFoundError("Prompt 版本不存在")
        # 重复发布保持幂等，不重新归档同用途的其他版本。
        if target.status == "published":
            return target
        now = datetime.now(UTC).replace(tzinfo=None)
        # 同一 prompt_key/variant 只能有一个发布版本，切换动作保持原子性。
        self.session.execute(
            update(PromptVersion)
            .where(
                PromptVersion.company_id == company_id,
                PromptVersion.assistant_id == assistant_id,
                PromptVersion.prompt_key == target.prompt_key,
                PromptVersion.variant == target.variant,
                PromptVersion.status == "published",
            )
            .values(status="archived", archived_at=now)
        )
        target.status = "published"
        target.published_by = published_by or None
        target.published_at = now
        self.session.commit()
        return target

    def get_knowledge_base(self, company_id: str, knowledge_base_id: int) -> KnowledgeBase:
        """按公司和主键读取未删除的知识库。"""
        row = self.session.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.company_id == self._company(company_id),
                KnowledgeBase.id == knowledge_base_id,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        if row is None:
            raise AdminNotFoundError("知识库不存在")
        return row

    def get_knowledge_base_by_key(self, company_id: str, knowledge_key: str) -> KnowledgeBase:
        """按公司和稳定业务标识读取未删除的知识库。"""
        row = self.session.scalar(
            select(KnowledgeBase).where(
                KnowledgeBase.company_id == self._company(company_id),
                KnowledgeBase.knowledge_key == knowledge_key,
                KnowledgeBase.deleted_at.is_(None),
            )
        )
        if row is None:
            raise AdminNotFoundError("知识库不存在")
        return row

    def create_knowledge_base(self, company_id: str, values: dict[str, Any]) -> KnowledgeBase:
        """在指定公司内创建知识库配置。"""
        return self._save(KnowledgeBase(company_id=self._company(company_id), **values))

    def list_knowledge_bases(self, company_id: str, status: str | None = None) -> list[KnowledgeBase]:
        """按公司列出未删除的知识库，可选状态过滤。"""
        statement = select(KnowledgeBase).where(
            KnowledgeBase.company_id == self._company(company_id), KnowledgeBase.deleted_at.is_(None)
        )
        if status:
            statement = statement.where(KnowledgeBase.status == status)
        return list(self.session.scalars(statement.order_by(KnowledgeBase.id.desc())).all())

    def update_knowledge_base(
        self, company_id: str, knowledge_base_id: int, values: dict[str, Any]
    ) -> KnowledgeBase:
        """更新知识库可变字段，并校验最终生效的切分参数组合。"""
        row = self.get_knowledge_base(company_id, knowledge_base_id)
        chunk_size = int(values.get("chunk_size", row.chunk_size))
        chunk_overlap = int(values.get("chunk_overlap", row.chunk_overlap))
        # 前端可能只修改一个切分参数，必须与数据库中的另一个参数合并校验。
        if chunk_overlap >= chunk_size:
            raise ValueError("chunk_overlap 必须小于 chunk_size")
        for key, value in values.items():
            setattr(row, key, value)
        return self._save(row)

    def get_data_source(self, company_id: str, data_source_id: int) -> DataSource:
        """按公司和主键读取未删除的数据源。"""
        row = self.session.scalar(
            select(DataSource).where(
                DataSource.company_id == self._company(company_id),
                DataSource.id == data_source_id,
                DataSource.deleted_at.is_(None),
            )
        )
        if row is None:
            raise AdminNotFoundError("数据源不存在")
        return row

    def create_data_source(self, company_id: str, values: dict[str, Any]) -> DataSource:
        """在指定公司内创建数据源配置。"""
        return self._save(DataSource(company_id=self._company(company_id), **values))

    def list_data_sources(self, company_id: str, status: str | None = None) -> list[DataSource]:
        """按公司列出未删除的数据源，可选状态过滤。"""
        statement = select(DataSource).where(
            DataSource.company_id == self._company(company_id), DataSource.deleted_at.is_(None)
        )
        if status:
            statement = statement.where(DataSource.status == status)
        return list(self.session.scalars(statement.order_by(DataSource.id.desc())).all())

    def update_data_source(
        self, company_id: str, data_source_id: int, values: dict[str, Any]
    ) -> DataSource:
        """在指定公司内更新数据源的展示、状态及同步配置。"""
        row = self.get_data_source(company_id, data_source_id)
        for key, value in values.items():
            setattr(row, key, value)
        return self._save(row)

    def bind_assistant_knowledge_base(
        self, company_id: str, values: dict[str, Any]
    ) -> AssistantKnowledgeBase:
        """按公司和双方 ID 创建或更新 Assistant-知识库绑定。"""
        company_id = self._company(company_id)
        self.get_assistant(company_id, values["assistant_id"])
        self.get_knowledge_base(company_id, values["knowledge_base_id"])
        row = self.session.scalar(
            select(AssistantKnowledgeBase).where(
                AssistantKnowledgeBase.company_id == company_id,
                AssistantKnowledgeBase.assistant_id == values["assistant_id"],
                AssistantKnowledgeBase.knowledge_base_id == values["knowledge_base_id"],
            )
        )
        if row is None:
            row = AssistantKnowledgeBase(company_id=company_id, **values)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        return self._save(row)

    def list_assistant_knowledge_base_bindings(
        self,
        company_id: str,
        *,
        assistant_id: int | None = None,
        knowledge_base_id: int | None = None,
        enabled: bool | None = None,
    ) -> list[AssistantKnowledgeBase]:
        """查询公司内的 Assistant-知识库绑定，可按任一关联字段过滤。"""
        statement = select(AssistantKnowledgeBase).where(
            AssistantKnowledgeBase.company_id == self._company(company_id)
        )
        if assistant_id is not None:
            statement = statement.where(AssistantKnowledgeBase.assistant_id == assistant_id)
        if knowledge_base_id is not None:
            statement = statement.where(
                AssistantKnowledgeBase.knowledge_base_id == knowledge_base_id
            )
        if enabled is not None:
            statement = statement.where(AssistantKnowledgeBase.enabled == enabled)
        return list(
            self.session.scalars(
                statement.order_by(
                    AssistantKnowledgeBase.priority.desc(),
                    AssistantKnowledgeBase.id.desc(),
                )
            ).all()
        )

    def bind_knowledge_base_source(self, company_id: str, values: dict[str, Any]) -> KnowledgeBaseSource:
        """按公司和双方 ID 创建或更新知识库-数据源绑定。"""
        company_id = self._company(company_id)
        self.get_knowledge_base(company_id, values["knowledge_base_id"])
        self.get_data_source(company_id, values["data_source_id"])
        row = self.session.scalar(
            select(KnowledgeBaseSource).where(
                KnowledgeBaseSource.company_id == company_id,
                KnowledgeBaseSource.knowledge_base_id == values["knowledge_base_id"],
                KnowledgeBaseSource.data_source_id == values["data_source_id"],
            )
        )
        if row is None:
            row = KnowledgeBaseSource(company_id=company_id, **values)
        else:
            for key, value in values.items():
                setattr(row, key, value)
        return self._save(row)

    def list_knowledge_base_source_bindings(
        self,
        company_id: str,
        *,
        knowledge_base_id: int | None = None,
        data_source_id: int | None = None,
        enabled: bool | None = None,
    ) -> list[KnowledgeBaseSource]:
        """查询公司内的知识库-数据源绑定，可按任一关联字段过滤。"""
        statement = select(KnowledgeBaseSource).where(
            KnowledgeBaseSource.company_id == self._company(company_id)
        )
        if knowledge_base_id is not None:
            statement = statement.where(
                KnowledgeBaseSource.knowledge_base_id == knowledge_base_id
            )
        if data_source_id is not None:
            statement = statement.where(KnowledgeBaseSource.data_source_id == data_source_id)
        if enabled is not None:
            statement = statement.where(KnowledgeBaseSource.enabled == enabled)
        return list(
            self.session.scalars(
                statement.order_by(
                    KnowledgeBaseSource.priority.desc(), KnowledgeBaseSource.id.desc()
                )
            ).all()
        )

    def create_ingest_job(
        self,
        company_id: str,
        knowledge_key: str,
        *,
        job_key: str,
        source: str,
        title: str,
        mime_type: str,
        storage_uri: str,
        content_sha256: str,
        created_by: str,
        permission_scope: dict[str, Any],
        parser: str,
        embedding_model: str,
    ) -> tuple[KnowledgeIngestJob, KnowledgeDocument, KnowledgeBase]:
        """在一个事务中创建可追踪文档版本和首次同步导入任务。"""
        company_id = self._company(company_id)
        knowledge_base = self.get_knowledge_base_by_key(company_id, knowledge_key)
        document_key = sha256(source.strip().encode()).hexdigest()
        latest_version = self.session.scalar(
            select(func.max(KnowledgeDocument.version)).where(
                KnowledgeDocument.company_id == company_id,
                KnowledgeDocument.knowledge_base_id == knowledge_base.id,
                KnowledgeDocument.document_key == document_key,
            )
        )
        document = KnowledgeDocument(
            company_id=company_id,
            knowledge_base_id=knowledge_base.id,
            document_key=document_key,
            source_type="upload",
            file_name=source.strip(),
            title=title.strip() or source.strip(),
            mime_type=mime_type,
            storage_uri=storage_uri,
            content_sha256=content_sha256,
            version=int(latest_version or 0) + 1,
            status="uploaded",
            permission_scope_json=permission_scope or None,
            created_by=created_by or None,
        )
        self.session.add(document)
        # Job 的外键依赖 document.id，flush 只分配主键，最终仍由同一次 commit 提交。
        self.session.flush()
        job = KnowledgeIngestJob(
            company_id=company_id,
            knowledge_base_id=knowledge_base.id,
            document_id=document.id,
            job_key=job_key,
            status="pending",
            parser=parser,
            embedding_model=embedding_model or None,
        )
        self.session.add(job)
        self.session.commit()
        return job, document, knowledge_base

    def get_ingest_job(
        self, company_id: str, job_id: int
    ) -> tuple[KnowledgeIngestJob, KnowledgeDocument, KnowledgeBase]:
        """按公司读取任务、文档和知识库，避免仅凭自增 ID 跨租户查询。"""
        company_id = self._company(company_id)
        job = self.session.scalar(
            select(KnowledgeIngestJob).where(
                KnowledgeIngestJob.company_id == company_id,
                KnowledgeIngestJob.id == job_id,
            )
        )
        if job is None:
            raise AdminNotFoundError("导入任务不存在")
        document = self.session.scalar(
            select(KnowledgeDocument).where(
                KnowledgeDocument.company_id == company_id,
                KnowledgeDocument.knowledge_base_id == job.knowledge_base_id,
                KnowledgeDocument.id == job.document_id,
                KnowledgeDocument.deleted_at.is_(None),
            )
        )
        if document is None:
            raise AdminNotFoundError("导入任务对应的文档不存在")
        knowledge_base = self.get_knowledge_base(
            company_id, job.knowledge_base_id
        )
        return job, document, knowledge_base

    def update_ingest_job(
        self,
        company_id: str,
        job_id: int,
        *,
        status: str,
        total_pages: int | None = None,
        parsed_pages: int | None = None,
        chunk_count: int | None = None,
        inserted_chunk_count: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> KnowledgeIngestJob:
        """同步更新任务阶段与文档状态，保留失败原因供状态页和重试使用。"""
        allowed = {"pending", "parsing", "embedding", "completed", "failed"}
        if status not in allowed:
            raise ValueError(f"不支持的导入任务状态：{status}")
        job, document, _ = self.get_ingest_job(company_id, job_id)
        now = datetime.now(UTC).replace(tzinfo=None)
        job.status = status
        if status in {"parsing", "embedding"} and job.started_at is None:
            job.started_at = now
        if status in {"completed", "failed"}:
            job.completed_at = now
        for key, value in {
            "total_pages": total_pages,
            "parsed_pages": parsed_pages,
            "chunk_count": chunk_count,
            "inserted_chunk_count": inserted_chunk_count,
        }.items():
            if value is not None:
                setattr(job, key, value)
        job.error_code = error_code
        job.error_message = error_message[:4000] if error_message else None
        document.status = {
            "pending": "uploaded",
            "parsing": "parsing",
            "embedding": "embedding",
            "completed": "published",
            "failed": "failed",
        }[status]
        if total_pages is not None:
            document.page_count = total_pages
        self.session.commit()
        return job

    def create_ingest_retry(
        self, company_id: str, failed_job_id: int, *, job_key: str
    ) -> tuple[KnowledgeIngestJob, KnowledgeDocument, KnowledgeBase]:
        """为失败文档创建新的任务记录，保留旧任务作为失败审计。"""
        failed_job, document, knowledge_base = self.get_ingest_job(
            company_id, failed_job_id
        )
        if failed_job.status != "failed":
            raise ValueError("只有 failed 状态的导入任务可以重试")
        job = KnowledgeIngestJob(
            company_id=failed_job.company_id,
            knowledge_base_id=failed_job.knowledge_base_id,
            document_id=failed_job.document_id,
            job_key=job_key,
            status="pending",
            parser=failed_job.parser,
            embedding_model=failed_job.embedding_model,
        )
        document.status = "uploaded"
        self.session.add(job)
        self.session.commit()
        return job, document, knowledge_base

    def runtime_config(
        self, company_id: str, knowledge_key: str = "", assistant_key: str = ""
    ) -> RagRuntimeConfig:
        """合并已启用知识库、绑定、已发布配置和 Prompt 的运行时设置。"""
        company_id = self._company(company_id)
        # 运行时读取必须同时受 company_id、Assistant 状态和绑定关系约束。
        knowledge_base = self.get_knowledge_base_by_key(company_id, knowledge_key) if knowledge_key else None
        if knowledge_base is not None and knowledge_base.status != "active":
            raise AdminNotFoundError("知识库未启用")
        binding = None
        system_context = ""
        model_overrides: dict[str, Any] = {}
        assistant_retrieval: dict[str, Any] = {}
        if assistant_key:
            # Assistant 未启用时，即使知识库本身有效也不能加载其 Prompt 或模型参数。
            assistant = self.get_assistant_by_key(company_id, assistant_key)
            if assistant.status != "active":
                raise AdminNotFoundError("Assistant 未启用")
            if assistant.published_config_version_id:
                # 仅接受指针指向且状态仍为 published 的配置，防止读取归档草稿。
                config = self.session.scalar(
                    select(AssistantConfigVersion).where(
                        AssistantConfigVersion.company_id == company_id,
                        AssistantConfigVersion.assistant_id == assistant.id,
                        AssistantConfigVersion.id == assistant.published_config_version_id,
                        AssistantConfigVersion.status == "published",
                    )
                )
                if config and isinstance(config.model_config_json, dict):
                    model_overrides.update(config.model_config_json)
                config_retrieval = getattr(config, "retrieval_config_json", None)
                if isinstance(config_retrieval, dict):
                    assistant_retrieval.update(config_retrieval)
            if knowledge_base is not None:
                # 显式提供 Assistant 和知识库时必须存在启用绑定，不能跨配置直接检索。
                binding = self.session.scalar(
                    select(AssistantKnowledgeBase).where(
                        AssistantKnowledgeBase.company_id == company_id,
                        AssistantKnowledgeBase.assistant_id == assistant.id,
                        AssistantKnowledgeBase.knowledge_base_id == knowledge_base.id,
                        AssistantKnowledgeBase.enabled.is_(True),
                    )
                )
                if binding is None:
                    raise AdminNotFoundError("Assistant 未绑定该知识库")
            # 当前知识问答固定使用已发布的 knowledge_answer/primary Prompt。
            prompt = self.session.scalar(
                select(PromptVersion).where(
                    PromptVersion.company_id == company_id,
                    PromptVersion.assistant_id == assistant.id,
                    PromptVersion.prompt_key == "knowledge_answer",
                    PromptVersion.variant == "primary",
                    PromptVersion.status == "published",
                )
            )
            system_context = prompt.content if prompt else ""
            if prompt and isinstance(prompt.model_overrides_json, dict):
                # Prompt 级参数覆盖 Assistant 配置，但不能改变连接凭据。
                model_overrides.update(prompt.model_overrides_json)
        # 绑定级检索参数优先于知识库默认值，未绑定场景直接使用知识库配置。
        retrieval = dict(assistant_retrieval)
        binding_retrieval = getattr(binding, "retrieval_config_json", None)
        if isinstance(binding_retrieval, dict):
            retrieval.update(binding_retrieval)
        top_k = retrieval.get("top_k")
        score_threshold = retrieval.get("score_threshold")
        policies = tuple(
            policy
            for policy in (
                getattr(knowledge_base, "permission_config_json", None),
                getattr(binding, "permission_filter_json", None),
            )
            if isinstance(policy, dict) and policy
        )
        return RagRuntimeConfig(
            collection=knowledge_base.milvus_collection if knowledge_base else "",
            system_context=system_context,
            model_overrides=model_overrides or None,
            chunk_size=int(knowledge_base.chunk_size) if knowledge_base else None,
            chunk_overlap=int(knowledge_base.chunk_overlap) if knowledge_base else None,
            top_k=int(top_k if top_k is not None else knowledge_base.default_top_k) if knowledge_base else None,
            score_threshold=(
                float(
                    score_threshold
                    if score_threshold is not None
                    else knowledge_base.default_score_threshold
                )
                if knowledge_base
                else None
            ),
            rerank_enabled=(
                retrieval.get("rerank_enabled")
                if isinstance(retrieval.get("rerank_enabled"), bool)
                else None
            ),
            rerank_candidates=(
                int(retrieval["rerank_candidates"])
                if retrieval.get("rerank_candidates") is not None
                else None
            ),
            permission_policies=policies,
        )

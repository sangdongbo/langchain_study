"""RAG 管理数据仓储，统一实施 company_id 隔离和版本发布事务。"""

from __future__ import annotations

import json
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, Literal

from sqlalchemy import func, inspect, or_, select, update
from sqlalchemy.orm import Session

from ai_erp_rag_assistant.app.assistant_catalog import APPROVAL_ASSISTANT_KEY

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
class RagKnowledgeBaseTarget:
    """公司级自动检索时的一个知识库目标。"""

    knowledge_base_key: str
    knowledge_base_name: str
    collection: str
    # 只允许已经发布且明确启用的文档参与检索；空元组由无 MySQL 的兼容模式使用。
    active_documents: tuple[tuple[str, str], ...] = ()
    document_scope_loaded: bool = False
    permission_policies: tuple[dict[str, Any], ...] = ()
    score_threshold: float | None = None

    def require_access(
        self,
        *,
        department: str,
        permission_tags: list[str],
        action: str = "read",
    ) -> None:
        """校验该知识库自己的权限策略，失败时只跳过该库而不影响其他库。"""
        _require_permission_policies(
            self.permission_policies,
            department=department,
            permission_tags=permission_tags,
            action=action,
        )


@dataclass(frozen=True)
class RagRuntimeConfig:
    """从公司级知识库、Assistant 配置和 Prompt 合并出的运行时参数。"""

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
    # 多知识库检索优先使用各 target 的独立策略；该字段保留给单库兼容调用。
    permission_policies: tuple[dict[str, Any], ...] = ()
    # 默认检索范围是当前公司的所有启用知识库；保留 collection 兼容旧导入接口。
    knowledge_bases: tuple[RagKnowledgeBaseTarget, ...] = ()
    # Assistant 配置的默认检索范围；请求级 search_scope 只允许收窄，不允许扩大范围。
    retrieval_scope: Literal["company_enabled", "selected"] = "company_enabled"

    def require_access(
        self,
        *,
        department: str,
        permission_tags: list[str],
        action: str = "read",
    ) -> None:
        """校验运行时知识库策略；身份标签必须来自已经验证的 ERP 用户。"""
        _require_permission_policies(
            self.permission_policies,
            department=department,
            permission_tags=permission_tags,
            action=action,
        )


def _require_permission_policies(
    policies: tuple[dict[str, Any], ...],
    *,
    department: str,
    permission_tags: list[str],
    action: str,
) -> None:
    """统一校验权限策略；多知识库检索时每个库独立调用。"""
    user_tags = {str(tag).strip() for tag in permission_tags if str(tag).strip()}
    department = department.strip()
    for policy in policies:
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
        if assistant_key.strip() == APPROVAL_ASSISTANT_KEY:
            raise ValueError("该 assistant_key 为系统审批助手保留键")
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
            Assistant.company_id == self._company(company_id),
            Assistant.assistant_key != APPROVAL_ASSISTANT_KEY,
            Assistant.deleted_at.is_(None),
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
                retrieval_scope=config.get("retrieval_scope") or "company_enabled",
                knowledge_base_keys_json=(
                    self._validate_selected_knowledge_bases(
                        company_id,
                        config.get("knowledge_base_keys") or [],
                    )
                    if (config.get("retrieval_scope") or "company_enabled") == "selected"
                    else None
                ),
                feature_flags_json=config["feature_flags"] or None,
                config_hash=_content_hash(config),
                created_by=created_by or None,
            )
        )

    def _validate_selected_knowledge_bases(
        self, company_id: str, knowledge_base_keys: list[str]
    ) -> list[str]:
        """校验配置中选择的知识库属于当前公司且处于启用状态。"""
        normalized: list[str] = []
        seen: set[str] = set()
        for raw_key in knowledge_base_keys:
            key = str(raw_key).strip()
            if not key or key in seen:
                continue
            normalized.append(key)
            seen.add(key)
        if not normalized:
            raise ValueError("retrieval_scope=selected 时至少选择一个知识库")
        # 逐个按 company_id 读取，既校验租户边界，也避免把无权知识库名称泄露给前端。
        for key in normalized:
            knowledge_base = self.get_knowledge_base_by_key(company_id, key)
            if knowledge_base.status != "active":
                raise AdminNotFoundError(f"知识库未启用：{key}")
        return normalized

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
        vector_version: str = "",
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
            vector_version=vector_version.strip() or None,
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

    def set_document_search_enabled(
        self,
        company_id: str,
        knowledge_key: str,
        *,
        source: str,
        version: str = "",
        enabled: bool,
    ) -> int:
        """只修改文件检索开关；实际删除和历史任务记录均保留。"""
        company_id = self._company(company_id)
        knowledge_base = self.get_knowledge_base_by_key(company_id, knowledge_key)
        source = source.strip()
        if not source:
            raise ValueError("source 不能为空")
        statement = select(KnowledgeDocument).where(
            KnowledgeDocument.company_id == company_id,
            KnowledgeDocument.knowledge_base_id == knowledge_base.id,
            KnowledgeDocument.file_name == source,
            KnowledgeDocument.deleted_at.is_(None),
        )
        normalized_version = version.strip()
        if normalized_version:
            # 新文档按 vector_version 匹配；兼容旧数据时同时接受内部整数版本号。
            clauses = [KnowledgeDocument.vector_version == normalized_version]
            if normalized_version.isdigit():
                clauses.append(KnowledgeDocument.version == int(normalized_version))
            statement = statement.where(or_(*clauses))
        rows = list(self.session.scalars(statement).all())
        if not rows:
            raise AdminNotFoundError("文档不存在")
        for row in rows:
            row.search_enabled = enabled
        self.session.commit()
        return len(rows)

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
        # completed 才允许检索；失败或处理中保持不可检索，避免半成品进入答案。
        document.search_enabled = status == "completed"
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
        document.search_enabled = True
        self.session.add(job)
        self.session.commit()
        return job, document, knowledge_base

    def runtime_config(
        self,
        company_id: str,
        knowledge_key: str = "",
        assistant_key: str = "",
        knowledge_base_keys: Sequence[str] = (),
        search_scope: Literal["company_enabled", "selected"] | None = None,
    ) -> RagRuntimeConfig:
        """合并 Assistant 配置和知识库目标，返回本次检索真正允许的范围。

        ``selected`` 模式优先使用已发布配置保存的知识库列表；请求级 Key 只能收窄
        已配置范围，不能借接口参数把一个专用 Assistant 扩大到全公司知识库。
        """
        company_id = self._company(company_id)
        requested_keys: list[str] = []
        seen_keys: set[str] = set()
        # 保留旧的单 Key 参数，同时接受前端新的多选数组。
        for raw_key in (*knowledge_base_keys, knowledge_key):
            key = str(raw_key or "").strip()
            if key and key not in seen_keys:
                requested_keys.append(key)
                seen_keys.add(key)

        if not assistant_key:
            # 未指定助手时取公司内最早创建的 active 助手，兼容单助手前端。
            scalar_query = getattr(self.session, "scalar", None)
            if callable(scalar_query):
                default_assistant = scalar_query(
                    select(Assistant)
                    .where(
                        Assistant.company_id == company_id,
                        Assistant.status == "active",
                        Assistant.deleted_at.is_(None),
                    )
                    .order_by(Assistant.id.asc())
                )
                assistant_key = str(
                    getattr(default_assistant, "assistant_key", None) or ""
                ).strip()

        system_context = ""
        model_overrides: dict[str, Any] = {}
        assistant_retrieval: dict[str, Any] = {}
        configured_scope: Literal["company_enabled", "selected"] = "company_enabled"
        configured_keys: list[str] = []
        legacy_binding = None
        assistant = None
        config = None
        if assistant_key:
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
                raw_scope = getattr(config, "retrieval_scope", "company_enabled")
                if raw_scope in {"company_enabled", "selected"}:
                    configured_scope = raw_scope
                raw_configured_keys = getattr(config, "knowledge_base_keys_json", None)
                if isinstance(raw_configured_keys, (list, tuple)):
                    configured_keys = [
                        str(key).strip()
                        for key in raw_configured_keys
                        if str(key).strip()
                    ]
        # 请求级 scope 只能明确收窄 company_enabled，不能绕过已发布 selected 配置。
        effective_scope = search_scope or (
            "selected" if requested_keys and configured_scope == "company_enabled" else configured_scope
        )
        if effective_scope == "company_enabled":
            if configured_scope == "selected":
                raise ValueError("当前 Assistant 已限定知识库范围，不能切换为 company_enabled")
            if requested_keys and search_scope == "company_enabled":
                raise ValueError("search_scope=company_enabled 时不能同时指定知识库")
            selected_keys: list[str] = []
        else:
            selected_keys = list(requested_keys or configured_keys)
            if not selected_keys:
                raise ValueError("retrieval_scope=selected 时至少选择一个知识库")
            if configured_scope == "selected" and configured_keys:
                configured_set = set(configured_keys)
                if any(key not in configured_set for key in selected_keys):
                    raise PermissionError("请求的知识库不在 Assistant 已配置范围内")

        # 指定范围时逐个读取并验证 active 状态；公司级模式读取当前公司的全部 active 库。
        if selected_keys:
            knowledge_bases = []
            for key in selected_keys:
                knowledge_base = self.get_knowledge_base_by_key(company_id, key)
                if knowledge_base.status != "active":
                    raise AdminNotFoundError(f"知识库未启用：{key}")
                knowledge_bases.append(knowledge_base)
        else:
            knowledge_bases = list(
                self.session.scalars(
                    select(KnowledgeBase)
                    .where(
                        KnowledgeBase.company_id == company_id,
                        KnowledgeBase.status == "active",
                        KnowledgeBase.deleted_at.is_(None),
                    )
                    .order_by(KnowledgeBase.id.asc())
                ).all()
            )
            if not knowledge_bases:
                raise AdminNotFoundError("当前公司没有启用的知识库")

        if assistant is not None and knowledge_key and knowledge_bases:
            # 历史绑定只保留权限/参数兼容读取，不再决定检索准入。
            legacy_binding = self.session.scalar(
                select(AssistantKnowledgeBase).where(
                    AssistantKnowledgeBase.company_id == company_id,
                    AssistantKnowledgeBase.assistant_id == assistant.id,
                    AssistantKnowledgeBase.knowledge_base_id == knowledge_bases[0].id,
                )
            )

        if assistant is not None:
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

        # 检索参数统一来自 Assistant/Prompt；知识库只保留切分和权限策略。
        if isinstance(getattr(legacy_binding, "retrieval_config_json", None), dict):
            assistant_retrieval.update(legacy_binding.retrieval_config_json)
        top_k = assistant_retrieval.get("top_k")
        score_threshold = assistant_retrieval.get("score_threshold")
        retrieval = dict(assistant_retrieval)
        targets: list[RagKnowledgeBaseTarget] = []
        for item in knowledge_bases:
            target_key = str(getattr(item, "knowledge_key", None) or "default")
            target_name = str(getattr(item, "name", None) or target_key)
            scalar_query = getattr(self.session, "scalars", None)
            documents = (
                scalar_query(
                    select(KnowledgeDocument)
                    .where(
                        KnowledgeDocument.company_id == company_id,
                        KnowledgeDocument.knowledge_base_id == item.id,
                        KnowledgeDocument.status == "published",
                        KnowledgeDocument.deleted_at.is_(None),
                        KnowledgeDocument.search_enabled.is_(True),
                    )
                    .order_by(KnowledgeDocument.id.asc())
                ).all()
                if callable(scalar_query)
                else []
            )
            active_document_pairs: list[tuple[str, str]] = []
            for document in documents:
                source = str(
                    document.file_name or document.title or document.document_key or ""
                )
                if not source:
                    continue
                vector_version = str(getattr(document, "vector_version", None) or "")
                active_document_pairs.append((source, vector_version))
                if not vector_version:
                    # 004 之前的旧向量可能没有字符串版本，兼容内部整数版本。
                    legacy_version = str(getattr(document, "version", "") or "")
                    if legacy_version and legacy_version != vector_version:
                        active_document_pairs.append((source, legacy_version))
            policy_values = [getattr(item, "permission_config_json", None)]
            if item is knowledge_bases[0] and knowledge_key:
                # 历史绑定的权限过滤只能收窄显式单库查询，绝不扩大公司级检索范围。
                policy_values.append(getattr(legacy_binding, "permission_filter_json", None))
            policies = tuple(
                policy for policy in policy_values if isinstance(policy, dict) and policy
            )
            targets.append(
                RagKnowledgeBaseTarget(
                    knowledge_base_key=target_key,
                    knowledge_base_name=target_name,
                    collection=str(getattr(item, "milvus_collection", "")),
                    active_documents=tuple(active_document_pairs),
                    # 没有 scalars 的旧测试 Session 视为未加载文档范围，保持兼容导入模式。
                    document_scope_loaded=callable(scalar_query),
                    permission_policies=policies,
                    score_threshold=(
                        float(item.default_score_threshold)
                        if item.default_score_threshold is not None
                        else None
                    ),
                )
            )
        policies = tuple(
            policy
            for target in targets
            for policy in target.permission_policies
        )
        first_target = targets[0] if len(targets) == 1 else None
        first_kb = knowledge_bases[0] if len(knowledge_bases) == 1 else None
        return RagRuntimeConfig(
            collection=first_target.collection if first_target else "",
            system_context=system_context,
            model_overrides=model_overrides or None,
            chunk_size=int(first_kb.chunk_size) if first_kb else None,
            chunk_overlap=int(first_kb.chunk_overlap) if first_kb else None,
            top_k=int(top_k) if top_k is not None else (int(first_kb.default_top_k) if first_kb else None),
            score_threshold=(
                float(score_threshold)
                if score_threshold is not None
                else (float(first_kb.default_score_threshold) if first_kb else None)
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
            retrieval_scope=("selected" if selected_keys else "company_enabled"),
            permission_policies=policies,
            knowledge_bases=tuple(targets),
        )

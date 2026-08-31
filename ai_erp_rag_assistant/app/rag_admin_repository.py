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
    PromptVersion,
)


class AdminNotFoundError(LookupError):
    pass


@dataclass(frozen=True)
class RagRuntimeConfig:
    collection: str
    system_context: str = ""
    # 已发布 Assistant 配置与知识问答 Prompt 合并后的安全模型参数。
    model_overrides: dict[str, Any] | None = None
    chunk_size: int | None = None
    chunk_overlap: int | None = None
    top_k: int | None = None
    score_threshold: float | None = None


def row_dict(row: Any) -> dict[str, Any]:
    state = inspect(row)
    return {
        attribute.key: None if attribute.key in state.unloaded else getattr(row, attribute.key)
        for attribute in state.mapper.column_attrs
        if attribute.key != "published_slot"
    }


def _content_hash(value: Any) -> str:
    canonical = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return sha256(canonical.encode()).hexdigest()


class RagAdminRepository:
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
        return self._save(
            Assistant(
                company_id=self._company(company_id),
                assistant_key=assistant_key,
                name=name,
                created_by=created_by or None,
            )
        )

    def list_assistants(self, company_id: str, status: str | None = None) -> list[Assistant]:
        statement = select(Assistant).where(
            Assistant.company_id == self._company(company_id), Assistant.deleted_at.is_(None)
        )
        if status:
            statement = statement.where(Assistant.status == status)
        return list(self.session.scalars(statement.order_by(Assistant.id.desc())).all())

    def create_config_version(
        self,
        company_id: str,
        assistant_id: int,
        config: dict[str, Any],
        created_by: str,
    ) -> AssistantConfigVersion:
        company_id = self._company(company_id)
        self.get_assistant(company_id, assistant_id)
        version = int(
            self.session.scalar(
                select(func.coalesce(func.max(AssistantConfigVersion.version), 0)).where(
                    AssistantConfigVersion.company_id == company_id,
                    AssistantConfigVersion.assistant_id == assistant_id,
                )
            )
            or 0
        ) + 1
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
        company_id = self._company(company_id)
        self.get_assistant(company_id, assistant_id)
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
        return self._save(KnowledgeBase(company_id=self._company(company_id), **values))

    def list_knowledge_bases(self, company_id: str, status: str | None = None) -> list[KnowledgeBase]:
        statement = select(KnowledgeBase).where(
            KnowledgeBase.company_id == self._company(company_id), KnowledgeBase.deleted_at.is_(None)
        )
        if status:
            statement = statement.where(KnowledgeBase.status == status)
        return list(self.session.scalars(statement.order_by(KnowledgeBase.id.desc())).all())

    def get_data_source(self, company_id: str, data_source_id: int) -> DataSource:
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
        return self._save(DataSource(company_id=self._company(company_id), **values))

    def list_data_sources(self, company_id: str, status: str | None = None) -> list[DataSource]:
        statement = select(DataSource).where(
            DataSource.company_id == self._company(company_id), DataSource.deleted_at.is_(None)
        )
        if status:
            statement = statement.where(DataSource.status == status)
        return list(self.session.scalars(statement.order_by(DataSource.id.desc())).all())

    def bind_assistant_knowledge_base(
        self, company_id: str, values: dict[str, Any]
    ) -> AssistantKnowledgeBase:
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

    def bind_knowledge_base_source(self, company_id: str, values: dict[str, Any]) -> KnowledgeBaseSource:
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

    def runtime_config(
        self, company_id: str, knowledge_key: str = "", assistant_key: str = ""
    ) -> RagRuntimeConfig:
        company_id = self._company(company_id)
        # 运行时读取必须同时受 company_id、Assistant 状态和绑定关系约束。
        knowledge_base = self.get_knowledge_base_by_key(company_id, knowledge_key) if knowledge_key else None
        if knowledge_base is not None and knowledge_base.status != "active":
            raise AdminNotFoundError("知识库未启用")
        binding = None
        system_context = ""
        model_overrides: dict[str, Any] = {}
        if assistant_key:
            assistant = self.get_assistant_by_key(company_id, assistant_key)
            if assistant.status != "active":
                raise AdminNotFoundError("Assistant 未启用")
            if assistant.published_config_version_id:
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
            if knowledge_base is not None:
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
        retrieval = binding.retrieval_config_json if binding and binding.retrieval_config_json else {}
        top_k = retrieval.get("top_k")
        score_threshold = retrieval.get("score_threshold")
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
        )

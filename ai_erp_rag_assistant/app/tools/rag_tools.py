"""供 LangGraph 工作流调用的租户级 RAG 检索工具。"""

from __future__ import annotations

from typing import Any

from ai_erp_rag_assistant.app.rag_admin_repository import RagRuntimeConfig
from ai_erp_rag_assistant.app.services.milvus_service import milvus_service
from ai_erp_rag_assistant.app.services.model_service import model_service
from ai_erp_rag_assistant.app.config import get_settings


def search_knowledge(
    query: str,
    *,
    company_id: str,
    department: str,
    permission_tags: list[str],
    top_k: int = 5,
    knowledge_base_key: str = "",
    runtime: RagRuntimeConfig | None = None,
) -> list[dict[str, Any]]:
    """按助手运行时配置执行权限过滤、多知识库召回和重排。"""
    settings = get_settings()
    # 未传运行时配置时保留旧的单 Collection 行为，方便独立 Graph 和本地调试。
    runtime = runtime or RagRuntimeConfig(
        collection="",
        rerank_enabled=settings.rag_rerank_enabled,
        rerank_candidates=settings.rag_rerank_candidates,
    )
    rerank_enabled = bool(runtime.rerank_enabled)
    candidate_count = (
        max(top_k, min(runtime.rerank_candidates or top_k, 50))
        if rerank_enabled
        else top_k
    )

    # 多目标或已加载文档发布范围时逐库检索，确保只搜索启用文档。
    if runtime.knowledge_bases and (
        len(runtime.knowledge_bases) > 1
        or any(target.document_scope_loaded for target in runtime.knowledge_bases)
    ):
        accessible_targets: list[dict[str, Any]] = []
        denied_count = 0
        for target in runtime.knowledge_bases:
            try:
                target.require_access(
                    department=department,
                    permission_tags=permission_tags,
                    action="read",
                )
            except PermissionError:
                denied_count += 1
                continue
            accessible_targets.append(
                {
                    "knowledge_base_key": target.knowledge_base_key,
                    "knowledge_base_name": target.knowledge_base_name,
                    "collection": target.collection,
                    "active_documents": target.active_documents,
                    "document_scope_loaded": target.document_scope_loaded,
                    "score_threshold": target.score_threshold,
                }
            )
        if not accessible_targets and denied_count:
            raise PermissionError("当前用户无权访问可用知识库")
        evidence = milvus_service.search_many(
            query,
            company_id=company_id,
            department=department,
            permission_tags=permission_tags,
            targets=accessible_targets,
            top_k=candidate_count,
            min_score=runtime.score_threshold,
        )
    else:
        runtime.require_access(
            department=department,
            permission_tags=permission_tags,
            action="read",
        )
        evidence = milvus_service.search(
            query,
            company_id=company_id,
            department=department,
            permission_tags=permission_tags,
            top_k=candidate_count,
            knowledge_base_key=knowledge_base_key,
            collection_name=runtime.collection,
            min_score=runtime.score_threshold,
        )
        # 单 Collection 的向量行不保存知识库名称，使用可信管理配置补齐引用来源。
        target = next(
            (
                item
                for item in runtime.knowledge_bases
                if item.knowledge_base_key == knowledge_base_key
            ),
            None,
        )
        if target is not None:
            evidence = [
                {
                    **item,
                    "knowledge_base_key": target.knowledge_base_key,
                    "knowledge_base_name": (
                        target.knowledge_base_name or target.knowledge_base_key
                    ),
                    "collection": target.collection,
                }
                for item in evidence
            ]

    if rerank_enabled:
        return model_service.rerank(
            query,
            evidence,
            top_k=top_k,
            model_overrides=runtime.model_overrides,
        )
    return [
        {**item, "retrieval_rank": index, "rank": index}
        for index, item in enumerate(evidence[:top_k], start=1)
    ]

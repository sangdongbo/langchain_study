"""供 LangGraph 工作流调用的租户级 RAG 检索工具。"""

from __future__ import annotations

from typing import Any

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
) -> list[dict[str, Any]]:
    """实际执行 Embedding -> Milvus dense search -> tenant/department filter。"""
    settings = get_settings()
    candidate_count = max(top_k, settings.rag_rerank_candidates)
    evidence = milvus_service.search(
        query,
        company_id=company_id,
        department=department,
        permission_tags=permission_tags,
        top_k=candidate_count if settings.rag_rerank_enabled else top_k,
        knowledge_base_key=knowledge_base_key,
    )
    if settings.rag_rerank_enabled:
        return model_service.rerank(query, evidence, top_k=top_k)
    return [
        {**item, "retrieval_rank": index, "rank": index}
        for index, item in enumerate(evidence[:top_k], start=1)
    ]

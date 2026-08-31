from __future__ import annotations

from typing import Any

from ai_erp_rag_assistant.app.services.milvus_service import milvus_service


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
    return milvus_service.search(
        query,
        company_id=company_id,
        department=department,
        permission_tags=permission_tags,
        top_k=top_k,
        knowledge_base_key=knowledge_base_key,
    )

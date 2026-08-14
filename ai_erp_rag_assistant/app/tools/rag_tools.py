from __future__ import annotations

from typing import Any

from ai_erp_rag_assistant.app.services.milvus_service import milvus_service


def search_knowledge(
    query: str,
    *,
    company_id: str,
    department: str,
    top_k: int = 5,
) -> list[dict[str, Any]]:
    """实际执行 Embedding -> Milvus dense search -> tenant/permission filter。"""
    return milvus_service.search(query, company_id=company_id, department=department, top_k=top_k)

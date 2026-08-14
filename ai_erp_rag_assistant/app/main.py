from __future__ import annotations

from fastapi import FastAPI

from ai_erp_rag_assistant.app.api import router
from ai_erp_rag_assistant.app.config import get_settings


app = FastAPI(
    title="AI ERP RAG Assistant",
    description="RAG + ERP Tool + LangGraph three-layer collaboration demo.",
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    settings = get_settings()
    return {
        "status": "ok",
        "milvus_uri": settings.milvus_uri,
        "milvus_collection": settings.milvus_collection,
        "erp_mode": settings.erp_mode,
        "llm_configured": str(bool(settings.llm_api_key)).lower(),
        "embedding_configured": str(bool(settings.embedding_api_key)).lower(),
    }

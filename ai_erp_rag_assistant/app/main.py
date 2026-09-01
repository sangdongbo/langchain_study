"""FastAPI 应用入口和不触发外部连接的健康检查。"""

from __future__ import annotations

from fastapi import FastAPI

from ai_erp_rag_assistant.app.api import router
from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.database import mysql_configured


app = FastAPI(
    title="AI ERP RAG Assistant",
    description="Enterprise RAG, ERP tools and LangGraph approval workflows.",
)
app.include_router(router)


@app.get("/health")
def health() -> dict[str, str]:
    """返回各组件是否已配置，不验证或暴露真实凭据。"""
    settings = get_settings()
    return {
        "status": "ok",
        "milvus_uri": settings.milvus_uri,
        "milvus_collection": settings.milvus_collection,
        "erp_mode": settings.erp_mode,
        "erp_read_mode": settings.erp_read_mode,
        "erp_write_mode": settings.erp_write_mode,
        "erp_skip_userinfo_validation": str(settings.erp_skip_userinfo_validation).lower(),
        "session_store": settings.session_store,
        "session_store_configured": str(
            settings.session_store != "mysql"
            or bool(settings.mysql_database and settings.mysql_user)
        ).lower(),
        "llm_configured": str(bool(settings.llm_api_key)).lower(),
        "embedding_configured": str(bool(settings.embedding_api_key)).lower(),
        "mysql_configured": str(mysql_configured(settings)).lower(),
        "langsmith_tracing": str(settings.langsmith_tracing).lower(),
        "langsmith_configured": str(bool(settings.langsmith_api_key)).lower(),
        "langsmith_project": settings.langsmith_project,
    }

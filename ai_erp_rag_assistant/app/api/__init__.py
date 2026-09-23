"""HTTP API 包，对应用入口只暴露总路由。"""

from ai_erp_rag_assistant.app.api.router import router


__all__ = ["router"]

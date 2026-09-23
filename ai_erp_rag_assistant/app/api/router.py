"""应用 API 总入口，只负责注册各业务路由。"""

from fastapi import APIRouter

from ai_erp_rag_assistant.app.api.routes import (
    approvals,
    assistants,
    chat,
    executions,
    rag,
    rag_admin,
    rag_documents,
    sessions,
    workbench,
)


router = APIRouter(prefix="/api")

router.include_router(rag_admin.router)
router.include_router(assistants.router)
router.include_router(chat.router)
router.include_router(executions.router)
router.include_router(rag.router)
router.include_router(rag_documents.router)
router.include_router(sessions.router)
router.include_router(approvals.router)
router.include_router(workbench.router)

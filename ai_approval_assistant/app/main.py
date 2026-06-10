from __future__ import annotations

from fastapi import FastAPI

from ai_approval_assistant.app.api.chat import router as chat_router
from ai_approval_assistant.app.api.health import router as health_router
from ai_approval_assistant.app.logging_config import configure_logging
from ai_approval_assistant.app.middleware import request_log_middleware

configure_logging()

app = FastAPI(title="AI Approval Assistant", version="0.1.0")
app.middleware("http")(request_log_middleware)
app.include_router(health_router)
app.include_router(chat_router)

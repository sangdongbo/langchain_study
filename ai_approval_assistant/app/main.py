from __future__ import annotations

from fastapi import FastAPI

from app.api.chat import router as chat_router
from app.api.health import router as health_router
from app.services.env_config_service import load_ai_approval_env
from app.logging_config import configure_logging
from app.middleware import request_log_middleware

load_ai_approval_env()
configure_logging()

app = FastAPI(title="AI Approval Assistant", version="0.1.0")
app.middleware("http")(request_log_middleware)
app.include_router(health_router)
app.include_router(chat_router)

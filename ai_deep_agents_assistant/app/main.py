from __future__ import annotations

from fastapi import FastAPI

from ai_deep_agents_assistant.app.api.chat import router as chat_router
from ai_deep_agents_assistant.app.api.health import router as health_router


app = FastAPI(title="AI Deep Agents Approval Assistant")
app.include_router(health_router)
app.include_router(chat_router)

from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from ai_deep_agents_assistant.app.api.chat import router as chat_router
from ai_deep_agents_assistant.app.api.health import router as health_router


app = FastAPI(title="AI Deep Agents Approval Assistant")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:8888",
        "http://127.0.0.1:8888",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(health_router)
app.include_router(chat_router)

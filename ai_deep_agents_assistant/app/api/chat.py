from __future__ import annotations

from fastapi import APIRouter

from ai_deep_agents_assistant.app.schemas.chat import ChatRequest, ChatResponse
from ai_deep_agents_assistant.app.services.chat_service import chat_service


router = APIRouter(prefix="/api/ai-approval", tags=["ai-approval"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Process one approval assistant chat turn."""
    return chat_service.run_turn(request)

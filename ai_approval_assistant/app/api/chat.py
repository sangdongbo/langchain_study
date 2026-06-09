from __future__ import annotations

from fastapi import APIRouter

from ai_approval_assistant.app.graph.workflow import run_chat_turn
from ai_approval_assistant.app.schemas.chat import ChatRequest, ChatResponse


router = APIRouter(prefix="/api/ai-approval", tags=["ai-approval"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    return run_chat_turn(request)

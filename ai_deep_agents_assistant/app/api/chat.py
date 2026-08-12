from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_deep_agents_assistant.app.schemas.chat import ChatRequest, ChatResponse
from ai_deep_agents_assistant.app.services.chat_service import chat_service
from ai_deep_agents_assistant.app.services.daily_report_api_client import (
    DailyReportApiError,
)
from ai_deep_agents_assistant.app.services.daily_report_service import (
    DailyReportSubmitError,
)


router = APIRouter(prefix="/api/ai-approval", tags=["ai-approval"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """Process one approval assistant chat turn."""
    try:
        return chat_service.run_turn(request)
    except (DailyReportSubmitError, DailyReportApiError) as exc:
        # ERP rejected the request, so return a message the web client can show.
        raise HTTPException(status_code=422, detail=str(exc)) from exc

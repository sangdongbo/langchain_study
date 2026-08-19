from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_deep_agents_assistant.app.schemas.chat import ChatRequest, ChatResponse
from ai_deep_agents_assistant.app.services.chat_service import chat_service
from ai_deep_agents_assistant.app.services.daily_report_api_client import (
    DailyReportAuthError,
    DailyReportApiError,
)
from ai_deep_agents_assistant.app.services.daily_report_service import (
    DailyReportSubmitError,
)


router = APIRouter(prefix="/api/ai-approval", tags=["ai-approval"])


@router.post("/chat", response_model=ChatResponse)
def chat(request: ChatRequest) -> ChatResponse:
    """处理审批助手的一轮对话。"""
    try:
        return chat_service.run_turn(request)
    except DailyReportAuthError as exc:
        # 认证失败使用标准 401，避免前端把所有 ERP 业务错误都误判为登录过期。
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    except (DailyReportSubmitError, DailyReportApiError) as exc:
        # ERP 拒绝请求时，返回可直接由前端展示的错误信息。
        raise HTTPException(status_code=422, detail=str(exc)) from exc

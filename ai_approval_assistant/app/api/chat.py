from __future__ import annotations
from fastapi import APIRouter, Header
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.chat_application_service import chat_application_service

router = APIRouter(prefix="/api/ai-approval", tags=["ai-approval"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> ChatResponse:
    """处理一轮审批助手聊天请求，并兼容从请求头透传 ERP 凭证。"""
    # API 层只做 HTTP 适配：把 header 中的 ERP 凭证补到请求模型里。
    if (not request.authorization and authorization) or (not request.uid and uid):
        request = request.model_copy(
            update={
                "authorization": request.authorization or authorization,
                "uid": request.uid or uid,
            }
        )
    # 业务编排交给应用服务层，避免 router 直接耦合 LangGraph 执行细节。
    return chat_application_service.run_turn(request)

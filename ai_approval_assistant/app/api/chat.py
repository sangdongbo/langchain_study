from __future__ import annotations
from fastapi import APIRouter, Header
from app.graph.approval_workflow import run_chat_turn
from app.schemas.chat import ChatRequest, ChatResponse

router = APIRouter(prefix="/api/ai-approval", tags=["ai-approval"])


@router.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> ChatResponse:
    """处理一轮审批助手聊天请求，并兼容从请求头透传 ERP 凭证。"""
    if (not request.authorization and authorization) or (not request.uid and uid):
        request = request.model_copy(
            update={
                "authorization": request.authorization or authorization,
                "uid": request.uid or uid,
            }
        )
    return run_chat_turn(request)

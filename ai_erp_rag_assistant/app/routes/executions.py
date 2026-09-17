"""ERP Agent Durable Execution 状态接口。"""

from __future__ import annotations

from fastapi import APIRouter, Header, HTTPException

# 统一 API 使用惰性代理，避免 `app.api` 反向注册时读取到半初始化模块。
from ai_erp_rag_assistant.app.api_compat import api_module
from ai_erp_rag_assistant.app.assistant_catalog import APPROVAL_ASSISTANT_KEY
from ai_erp_rag_assistant.app.schemas import (
    ExecutionStatusRequest,
    ExecutionStatusResponse,
)
from ai_erp_rag_assistant.app.services.execution_repository import (
    ExecutionNotFoundError,
    execution_repository,
)


router = APIRouter(tags=["Executions"])


@router.post("/executions/status", response_model=ExecutionStatusResponse)
def execution_status(
    request: ExecutionStatusRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> ExecutionStatusResponse:
    """查询当前登录用户的一次 ERP Agent 运行状态。"""
    request, _, company_id, user_id = api_module._persistent_identity(
        request,
        authorization,
        uid,
    )
    assistant_key = request.assistant_key.strip() or APPROVAL_ASSISTANT_KEY
    if assistant_key != APPROVAL_ASSISTANT_KEY:
        raise HTTPException(status_code=422, detail="Durable Execution 仅用于 ERP 审批助手")
    if not execution_repository.enabled:
        raise HTTPException(
            status_code=503,
            detail="Durable Execution 未启用，请配置 AI_ERP_SESSION_STORE=mysql",
        )
    try:
        item = execution_repository.get_status(
            company_id=company_id,
            assistant_key=assistant_key,
            user_id=user_id,
            run_key=request.run_id,
        )
    except ExecutionNotFoundError as exc:
        # 无权限与不存在统一返回 404，避免泄露其他租户或用户的运行标识。
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"读取 ERP Agent 运行失败：{exc}") from exc
    return ExecutionStatusResponse.model_validate(item)

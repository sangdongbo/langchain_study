"""面向业务页面的统一助手目录接口。"""

from __future__ import annotations

from typing import Annotated, Any

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ai_erp_rag_assistant.app import api as api_module
from ai_erp_rag_assistant.app.assistant_catalog import approval_assistant_item
from ai_erp_rag_assistant.app.database import get_optional_db_session
from ai_erp_rag_assistant.app.rag_admin_repository import RagAdminRepository, row_dict
from ai_erp_rag_assistant.app.schemas import AssistantListRequest


router = APIRouter(tags=["Assistants"])


@router.post("/assistants/list")
def assistant_list(
    request: AssistantListRequest,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
) -> dict[str, Any]:
    """合并固定审批助手和当前公司的 RAG 助手。"""
    _, _, company_id, _ = api_module._persistent_identity(
        request, authorization, uid
    )
    items: list[dict[str, Any]] = []
    if request.status in (None, "active"):
        items.append(approval_assistant_item())
    if db is not None:
        try:
            rows = RagAdminRepository(db).list_assistants(company_id, request.status)
            items.extend(
                {
                    **row_dict(row),
                    "assistant_type": "rag",
                    "is_system": False,
                }
                for row in rows
            )
        except SQLAlchemyError as exc:
            db.rollback()
            raise HTTPException(status_code=503, detail="MySQL 读取助手列表失败") from exc
    return {"items": items, "count": len(items)}

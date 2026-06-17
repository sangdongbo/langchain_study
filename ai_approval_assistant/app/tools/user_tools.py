from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.schemas.approval import UserContext
from app.services.user_service import user_service


class UserToolInput(BaseModel):
    user_id: str = Field(description="业务用户 ID。")
    uid: str | None = Field(default=None, description="ERP UID。")
    authorization: str | None = Field(default=None, description="ERP Authorization。")


@tool(args_schema=UserToolInput)
def get_current_user_info(
    user_id: str,
    uid: str | None = None,
    authorization: str | None = None,
) -> dict[str, Any]:
    """获取当前登录用户的基础信息。"""
    user = UserContext(
        user_id=user_id,
        name=f"User {user_id}",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid=uid,
        authorization=authorization,
    )
    return user_service.get_userinfo(user)


@tool(args_schema=UserToolInput)
def get_user_superior_info(
    user_id: str,
    uid: str | None = None,
    authorization: str | None = None,
) -> dict[str, Any]:
    """获取当前登录用户的直属上级信息。"""
    user = UserContext(
        user_id=user_id,
        name=f"User {user_id}",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid=uid,
        authorization=authorization,
    )
    return user_service.get_superior_info(user)


USER_TOOLS = [get_current_user_info, get_user_superior_info]

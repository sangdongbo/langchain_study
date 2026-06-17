from __future__ import annotations

from typing import Any, Protocol

from app.schemas.approval import UserContext
from app.services.user_api_client import UserApiClient


class UserInfoApiClient(Protocol):
    def get_userinfo(self, user: UserContext) -> dict[str, Any]:
        ...


class UserService:
    """用户信息业务服务。"""

    def __init__(self, api_client: UserInfoApiClient | None = None) -> None:
        self._api_client = api_client or UserApiClient()

    def get_userinfo(self, user: UserContext) -> dict[str, Any]:
        """获取并标准化当前登录用户信息。"""
        if not user.authorization or not user.uid:
            return {}
        payload = self._api_client.get_userinfo(user)
        if payload.get("code") != 200:
            raise ValueError(f"userinfo returned code {payload.get('code')}")
        data = payload.get("data")
        if not isinstance(data, dict):
            return {}
        return _normalize_userinfo(data)

    def get_superior_info(self, user: UserContext) -> dict[str, Any]:
        """根据当前用户的 superior_id 获取直属上级信息。"""
        current_user = self.get_userinfo(user)
        superior_id = str(current_user.get("superior_id") or "").strip()
        if not superior_id or superior_id == "0":
            return {}
        superior_user = user.model_copy(update={"uid": superior_id})
        return self.get_userinfo(superior_user)


def _normalize_userinfo(data: dict[str, Any]) -> dict[str, Any]:
    """把 ERP 用户信息整理成 agent 更容易消费的结构。"""
    uid = data.get("uid") or data.get("id") or data.get("user_id")
    name = data.get("name") or data.get("display_name") or data.get("realname")
    display_name = data.get("display_name") or name
    dept_id = data.get("dept_id") or data.get("department_id")
    superior_id = data.get("superior_id") or data.get("superior_uid")
    department_name = (
        data.get("department_name")
        or data.get("dept_name")
        or data.get("department")
    )
    return {
        "uid": str(uid or ""),
        "name": str(name or ""),
        "display_name": str(display_name or ""),
        "avatar": _optional_text(data.get("avatar")),
        "mobile": _optional_text(data.get("mobile") or data.get("phone")),
        "email": _optional_text(data.get("email")),
        "company_id": str(data.get("company_id") or ""),
        "dept_id": str(dept_id or ""),
        "department_name": _optional_text(department_name),
        "superior_id": str(superior_id or "0"),
        "raw": data,
    }


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


user_service = UserService()

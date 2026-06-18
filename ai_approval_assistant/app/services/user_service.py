from __future__ import annotations

from typing import Any, Protocol

from app.schemas.approval import UserContext
from app.services.user_api_client import UserApiClient


class UserInfoApiClient(Protocol):
    def get_userinfo(self, user: UserContext) -> dict[str, Any]:
        ...

    def get_user_detail(self, user: UserContext, user_id: str) -> dict[str, Any]:
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
        return self.get_user_detail(user, superior_id)

    def get_user_detail(self, user: UserContext, user_id: str) -> dict[str, Any]:
        """获取并标准化指定用户详情。"""
        payload = self._api_client.get_user_detail(user, user_id)
        if payload.get("code") != 200:
            raise ValueError(f"user detail returned code {payload.get('code')}")
        data = payload.get("data")
        if not isinstance(data, dict):
            return {}
        return _normalize_userinfo(data)


def _normalize_userinfo(data: dict[str, Any]) -> dict[str, Any]:
    """把 ERP 用户信息整理成 agent 更容易消费的结构。"""
    user_data = data.get("user") if isinstance(data.get("user"), dict) else data
    uid = _field_value(user_data.get("uid") or user_data.get("id") or user_data.get("user_id"))
    name = _field_value(
        user_data.get("name") or user_data.get("display_name") or user_data.get("realname")
    )
    display_name = _field_value(user_data.get("display_name")) or name
    dept_id = _field_value(user_data.get("dept_id") or user_data.get("department_id"))
    superior_id = _field_value(user_data.get("superior_id") or user_data.get("superior_uid"))
    department_name = (
        _field_text(user_data.get("department_id"))
        or _field_value(user_data.get("department_name"))
        or _field_value(user_data.get("dept_name"))
        or _field_value(user_data.get("department"))
    )
    return {
        "uid": str(uid or ""),
        "name": str(name or ""),
        "display_name": str(display_name or ""),
        "avatar": _optional_text(_field_value(user_data.get("avatar"))),
        "mobile": _optional_text(_field_value(user_data.get("mobile") or user_data.get("phone"))),
        "email": _optional_text(_field_value(user_data.get("email"))),
        "company_id": str(_field_value(user_data.get("company_id")) or ""),
        "dept_id": str(dept_id or ""),
        "department_name": _optional_text(department_name),
        "superior_id": str(superior_id or "0"),
        "raw": data,
    }


def _field_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        nested_value = value.get("value")
        if isinstance(nested_value, list):
            return nested_value[0] if nested_value else None
        return nested_value
    return value


def _field_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    text = value.get("text")
    if isinstance(text, list) and text:
        first = text[0]
        if isinstance(first, dict):
            return _optional_text(first.get("department_name") or first.get("name"))
        return _optional_text(first)
    return _optional_text(text)


def _optional_text(value: Any) -> str | None:
    text = str(value or "").strip()
    return text or None


user_service = UserService()

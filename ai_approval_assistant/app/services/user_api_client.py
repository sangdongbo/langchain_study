from __future__ import annotations

from typing import Any

import httpx

from app.schemas.approval import UserContext
from app.services.crm_api_client import DebugLogWriter, _crm_headers
from app.services.crm_config_service import load_crm_endpoint_config
from app.services.debug_log_service import write_debug_log


class UserApiClient:
    """ERP 用户相关接口调用封装。"""

    def __init__(
        self,
        http_client: httpx.Client | None = None,
        userinfo_url: str | None = None,
        user_detail_url: str | None = None,
        log_writer: DebugLogWriter | None = None,
    ) -> None:
        endpoint_config = load_crm_endpoint_config()
        self._http_client = http_client or httpx.Client(timeout=30)
        self._userinfo_url = userinfo_url or endpoint_config.userinfo_url
        self._user_detail_url = user_detail_url or endpoint_config.user_detail_url
        self._log_writer = log_writer or write_debug_log

    def get_userinfo(self, user: UserContext) -> dict[str, Any]:
        """调用 /api/User/userinfo 获取当前登录用户信息。"""
        return self._post_json("user.userinfo", self._userinfo_url, user, {})

    def get_user_detail(self, user: UserContext, user_id: str) -> dict[str, Any]:
        """调用 /api/person/userDetails 获取指定用户详情。"""
        return self._post_json(
            "person.userDetails",
            self._user_detail_url,
            user,
            {"user_id": int(user_id)},
        )

    def _post_json(
        self,
        event: str,
        url: str,
        user: UserContext,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        headers = _crm_headers(user)
        self._log_writer(
            f"crm.{event}.request",
            {
                "url": url,
                "headers": headers,
                "body": body,
            },
        )
        response = self._http_client.post(url, headers=headers, json=body)
        response.raise_for_status()
        payload = response.json()
        data = payload.get("data")
        self._log_writer(
            f"crm.{event}.response",
            {
                "code": payload.get("code"),
                "message": payload.get("message"),
                "data_type": type(data).__name__,
                **_user_data_log_summary(data),
            },
        )
        return payload


def _user_data_log_summary(data: Any) -> dict[str, Any]:
    """只记录排查组织关系需要的低风险字段。"""
    if not isinstance(data, dict):
        return {}
    user_data = data.get("user") if isinstance(data.get("user"), dict) else data
    preview_keys = (
        "id",
        "uid",
        "user_id",
        "superior_id",
        "superior_uid",
        "parent_id",
        "leader_id",
        "manager_id",
    )
    return {
        "data_keys": sorted(str(key) for key in data.keys()),
        "data_preview": {key: user_data.get(key) for key in preview_keys},
    }

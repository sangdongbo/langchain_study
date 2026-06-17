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
        log_writer: DebugLogWriter | None = None,
    ) -> None:
        self._http_client = http_client or httpx.Client(timeout=10)
        self._userinfo_url = userinfo_url or load_crm_endpoint_config().userinfo_url
        self._log_writer = log_writer or write_debug_log

    def get_userinfo(self, user: UserContext) -> dict[str, Any]:
        """调用 /api/User/userinfo 获取当前登录用户信息。"""
        return self._post_json("user.userinfo", self._userinfo_url, user, {})

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
        self._log_writer(
            f"crm.{event}.response",
            {
                "code": payload.get("code"),
                "message": payload.get("message"),
                "data_type": type(payload.get("data")).__name__,
            },
        )
        return payload

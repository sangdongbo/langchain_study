from __future__ import annotations

import os
from typing import Any

import httpx

from ai_deep_agents_assistant.app.services.env_config import load_project_env
from ai_deep_agents_assistant.app.services.request_context import ErpRequestContext


DEFAULT_ERP_BASE_URL = "https://dev2.lanerp.com"
DEFAULT_SYNC_TYPES = [
    "process",
    "followup",
    "order",
    "work_ticket",
    "customer_manage",
]


class DailyReportApiError(RuntimeError):
    """携带接口上下文的 ERP 日报请求异常。"""


class DailyReportApiClient:
    def __init__(
        self,
        http_client: httpx.Client | None = None,
        base_url: str | None = None,
    ) -> None:
        load_project_env()
        self._http_client = http_client or httpx.Client(timeout=20)
        self._base_url = (
            base_url
            or os.getenv("AI_DEEP_AGENT_ERP_BASE_URL")
            or os.getenv("AI_APPROVAL_CRM_BASE_URL")
            or DEFAULT_ERP_BASE_URL
        ).rstrip("/")

    def get_form_fields(self, user: ErpRequestContext) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/field/formFields",
            user,
            json={"field_form": "daily_reports"},
        )

    def get_config(self, user: ErpRequestContext) -> dict[str, Any]:
        return self._request(
            "GET",
            "/oa/dailyReport/config/get",
            user,
            params={"need_parse": 1},
        )

    def get_draft(
        self,
        user: ErpRequestContext,
        report_type: int,
        report_date: str,
    ) -> dict[str, Any]:
        return self._request(
            "GET",
            "/oa/dailyReport/draft/get",
            user,
            params={"type": report_type, "date": report_date},
        )

    def sync_data(
        self,
        user: ErpRequestContext,
        report_type: int,
        report_date: str,
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/api/oa/dailyReport/syncData",
            user,
            json={
                "daily_report_type": report_type,
                "sync_type": DEFAULT_SYNC_TYPES,
                "date_range": [report_date, report_date],
            },
        )

    def add_daily_report(
        self,
        user: ErpRequestContext,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        return self._request(
            "POST",
            "/oa/dailyReport/add",
            user,
            json=payload,
        )

    def _request(
        self,
        method: str,
        path: str,
        user: ErpRequestContext,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        try:
            response = self._http_client.request(
                method,
                f"{self._base_url}{path}",
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json;charset=UTF-8",
                    "Authorization": user.authorization,
                    "UID": user.uid,
                },
                params=params,
                json=json,
            )
            response.raise_for_status()
            payload = response.json()
        except httpx.TimeoutException as exc:
            raise DailyReportApiError(f"日报接口请求超时：{method} {path}") from exc
        except httpx.HTTPStatusError as exc:
            raise DailyReportApiError(
                f"日报接口请求失败：{method} {path}，HTTP {exc.response.status_code}"
            ) from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise DailyReportApiError(
                f"日报接口请求失败：{method} {path}，{exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise DailyReportApiError(f"日报接口返回格式错误：{method} {path}")
        return payload

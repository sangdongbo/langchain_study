from __future__ import annotations

from typing import Any

import httpx

from app.schemas.approval import UserContext
from app.services.crm_config_service import (
    _join_url,
    _trim_base_url,
    load_crm_endpoint_config,
)

DEFAULT_DAILY_REPORT_SYNC_TYPES = [
    "process",
    "followup",
    "order",
    "work_ticket",
    "customer_manage",
]


class DailyReportApiClient:
    """ERP 日报接口调用封装。"""

    def __init__(self, http_client: httpx.Client | None = None, base_url: str | None = None) -> None:
        self._http_client = http_client or httpx.Client(timeout=10)
        self._base_url = _trim_base_url(base_url or _base_url_from_config())

    def get_form_fields(self, user: UserContext) -> dict[str, Any]:
        return self._post(
            user,
            "/api/field/formFields",
            {"field_form": "daily_reports"},
        )

    def get_config(self, user: UserContext) -> dict[str, Any]:
        response = self._http_client.get(
            _join_url(self._base_url, "/oa/dailyReport/config/get"),
            headers=_headers(user),
            params={"need_parse": 1},
        )
        response.raise_for_status()
        return response.json()

    def get_draft(self, user: UserContext, report_type: int, report_date: str) -> dict[str, Any]:
        response = self._http_client.get(
            _join_url(self._base_url, "/oa/dailyReport/draft/get"),
            headers=_headers(user),
            params={"type": report_type, "date": report_date},
        )
        response.raise_for_status()
        return response.json()

    def set_draft(self, user: UserContext, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(user, "/oa/dailyReport/config/draft/set", payload)

    def sync_data(self, user: UserContext, report_type: int, report_date: str) -> dict[str, Any]:
        return self._post(
            user,
            "/api/oa/dailyReport/syncData",
            {
                "daily_report_type": report_type,
                "sync_type": DEFAULT_DAILY_REPORT_SYNC_TYPES,
                "date_range": [report_date, report_date],
            },
        )

    def add_daily_report(self, user: UserContext, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post(user, "/oa/dailyReport/add", payload)

    def _post(
        self, user: UserContext, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        response = self._http_client.post(
            _join_url(self._base_url, path),
            headers=_headers(user),
            json=payload,
        )
        response.raise_for_status()
        return response.json()


def _headers(user: UserContext) -> dict[str, str]:
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": user.authorization or "",
        "UID": user.uid or "",
    }


def _base_url_from_config() -> str:
    approval_list_url = load_crm_endpoint_config().approval_list_url
    marker = "/api/approval/list"
    if approval_list_url.endswith(marker):
        return approval_list_url[: -len(marker)]
    return approval_list_url

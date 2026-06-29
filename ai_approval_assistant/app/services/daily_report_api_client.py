from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from app.schemas.approval import UserContext
from app.services.crm_config_service import (
    _join_url,
    _trim_base_url,
    load_crm_endpoint_config,
)
from app.services.debug_log_service import write_debug_log

DebugLogWriter = Callable[[str, dict[str, Any]], None]

DEFAULT_DAILY_REPORT_SYNC_TYPES = [
    "process",
    "followup",
    "order",
    "work_ticket",
    "customer_manage",
]


class DailyReportApiError(RuntimeError):
    """日报外部接口调用失败，携带前端和日志都能识别的接口上下文。"""

    def __init__(self, event: str, method: str, path: str, detail: str) -> None:
        self.event = event
        self.method = method
        self.path = path
        self.detail = detail
        super().__init__(f"日报接口请求失败：{method} {path}，{detail}")


class DailyReportApiClient:
    """ERP 日报接口调用封装。"""

    def __init__(
        self,
        http_client: httpx.Client | None = None,
        base_url: str | None = None,
        clock: Any | None = None,
        log_writer: DebugLogWriter | None = None,
    ) -> None:
        self._http_client = http_client or httpx.Client(timeout=10)
        self._base_url = _trim_base_url(base_url or _base_url_from_config())
        self._clock = clock or time.monotonic
        self._log_writer = log_writer or write_debug_log

    def get_form_fields(self, user: UserContext) -> dict[str, Any]:
        return self._post(
            "field.formFields",
            user,
            "/api/field/formFields",
            {"field_form": "daily_reports"},
        )

    def get_config(self, user: UserContext) -> dict[str, Any]:
        return self._request_json(
            "config.get",
            "GET",
            user,
            "/oa/dailyReport/config/get",
            params={"need_parse": 1},
        )

    def get_draft(self, user: UserContext, report_type: int, report_date: str) -> dict[str, Any]:
        return self._request_json(
            "draft.get",
            "GET",
            user,
            "/oa/dailyReport/draft/get",
            params={"type": report_type, "date": report_date},
        )

    def set_draft(self, user: UserContext, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("draft.set", user, "/oa/dailyReport/config/draft/set", payload)

    def sync_data(self, user: UserContext, report_type: int, report_date: str) -> dict[str, Any]:
        return self._post(
            "syncData",
            user,
            "/api/oa/dailyReport/syncData",
            {
                "daily_report_type": report_type,
                "sync_type": DEFAULT_DAILY_REPORT_SYNC_TYPES,
                "date_range": [report_date, report_date],
            },
        )

    def add_daily_report(self, user: UserContext, payload: dict[str, Any]) -> dict[str, Any]:
        return self._post("add", user, "/oa/dailyReport/add", payload)

    def _post(
        self, event: str, user: UserContext, path: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        return self._request_json(
            event,
            "POST",
            user,
            path,
            json=payload,
        )

    def _request_json(
        self,
        event: str,
        method: str,
        user: UserContext,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """统一发送日报接口请求，并把失败包装成可读的日报业务错误。"""
        url = _join_url(self._base_url, path)
        headers = _headers(user)
        started_at = self._clock()
        status_code: int | None = None
        try:
            self._log_request(event, method, url, headers, params, json)
            response = self._http_client.request(
                method,
                url,
                headers=headers,
                params=params,
                json=json,
            )
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            self._log_response(event, payload)
            self._log_timing(event, url, started_at, self._clock(), True, status_code)
            return payload
        except httpx.TimeoutException as exc:
            self._log_timing(
                event,
                url,
                started_at,
                self._clock(),
                False,
                status_code,
                str(exc),
            )
            raise DailyReportApiError(event, method, path, "请求超时") from exc
        except httpx.HTTPStatusError as exc:
            self._log_timing(
                event,
                url,
                started_at,
                self._clock(),
                False,
                status_code,
                str(exc),
            )
            raise DailyReportApiError(
                event,
                method,
                path,
                f"HTTP 状态码 {exc.response.status_code}",
            ) from exc
        except httpx.HTTPError as exc:
            self._log_timing(
                event,
                url,
                started_at,
                self._clock(),
                False,
                status_code,
                str(exc),
            )
            raise DailyReportApiError(event, method, path, str(exc) or "HTTP 请求失败") from exc

    def _log_request(
        self,
        event: str,
        method: str,
        url: str,
        headers: dict[str, str],
        params: dict[str, Any] | None,
        body: dict[str, Any] | None,
    ) -> None:
        """记录日报接口请求，Authorization 会由日志服务统一脱敏。"""
        payload: dict[str, Any] = {
            "method": method,
            "url": url,
            "headers": headers,
        }
        if params:
            payload["params"] = params
        if body is not None:
            payload["body"] = body
        self._log_writer(f"daily_report.{event}.request", payload)

    def _log_response(self, event: str, payload: dict[str, Any]) -> None:
        """记录日报接口响应摘要，避免草稿和同步数据过大时刷屏。"""
        data = payload.get("data")
        summary: dict[str, Any] = {
            "code": payload.get("code"),
            "message": payload.get("message"),
            "data_type": type(data).__name__,
        }
        if isinstance(data, list):
            summary["data_count"] = len(data)
            summary["data_sample"] = data[:2]
        elif isinstance(data, dict):
            summary["data_keys"] = list(data.keys())[:20]
            summary["data_sample"] = data
        else:
            summary["data"] = data
        self._log_writer(f"daily_report.{event}.response", summary)

    def _log_timing(
        self,
        event: str,
        url: str,
        started_at: float,
        finished_at: float,
        success: bool,
        status_code: int | None,
        error: str | None = None,
    ) -> None:
        """记录日报接口耗时；排查超时问题时主要看这里。"""
        payload: dict[str, Any] = {
            "url": url,
            "duration_ms": max(0, int((finished_at - started_at) * 1000)),
            "success": success,
            "status_code": status_code,
        }
        if error:
            payload["error"] = error[:300]
        self._log_writer(f"daily_report.{event}.timing", payload)


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

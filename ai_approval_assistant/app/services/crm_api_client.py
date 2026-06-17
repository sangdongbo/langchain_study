from __future__ import annotations

import time
from typing import Any, Callable

import httpx

from app.schemas.approval import UserContext
from app.services.crm_config_service import load_crm_endpoint_config
from app.services.debug_log_service import write_debug_log

DebugLogWriter = Callable[[str, dict[str, Any]], None]


class CrmApiClient:
    """ERP/CRM 审批接口调用封装。

    这里只负责组织请求、发送 HTTP、记录接口日志；响应语义解析仍放在
    CrmApprovalService，避免接口传输层和审批业务规则混在一起。
    """

    def __init__(
        self,
        http_client: httpx.Client | None = None,
        approval_list_url: str | None = None,
        form_fields_url: str | None = None,
        get_nodes_url: str | None = None,
        add_approval_url: str | None = None,
        related_list_url: str | None = None,
        holiday_rule_url: str | None = None,
        clock: Any | None = None,
        log_writer: DebugLogWriter | None = None,
    ) -> None:
        self._http_client = http_client or httpx.Client(timeout=10)
        self._clock = clock or time.monotonic
        self._log_writer = log_writer or write_debug_log
        endpoint_config = load_crm_endpoint_config()
        self._approval_list_url = approval_list_url or endpoint_config.approval_list_url
        self._form_fields_url = form_fields_url or endpoint_config.form_fields_url
        self._get_nodes_url = get_nodes_url or endpoint_config.get_nodes_url
        self._add_approval_url = add_approval_url or endpoint_config.add_approval_url
        self._related_list_url = related_list_url or endpoint_config.related_list_url
        self._holiday_rule_url = holiday_rule_url or endpoint_config.holiday_rule_url

    def list_approvals(self, user: UserContext, keyword: str = "") -> dict[str, Any]:
        """调用 /api/approval/list 查询审批模板。"""
        return self._post_crm_json(
            "approval.list",
            self._approval_list_url,
            user,
            {"keyword": keyword},
        )

    def get_form_fields(self, user: UserContext, template_id: str) -> dict[str, Any]:
        """调用 /api/field/formFields 获取模板字段。"""
        return self._post_crm_json(
            "field.formFields",
            self._form_fields_url,
            user,
            {"field_form": f"approval_type_{template_id}"},
        )

    def get_approval_nodes(
        self,
        user: UserContext,
        approval_set_id: str,
        form_value: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """调用 /api/approval/getNodes 获取审批流程节点。"""
        return self._post_crm_json(
            "approval.getNodes",
            self._get_nodes_url,
            user,
            {
                "approval_set_id": int(approval_set_id),
                "form_value": form_value,
            },
        )

    def get_related_list(
        self,
        user: UserContext,
        relate_type: str,
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """调用 /api/Company/getRelatedList 获取关联业务对象。"""
        return self._post_crm_json(
            "company.getRelatedList",
            self._related_list_url,
            user,
            {
                "relate_type": relate_type,
                "page": page,
                "pageSize": page_size,
                "keyword": keyword,
                "status": 0,
                "created_at": "",
                "hasNoAccess": False,
                "type": "",
            },
        )

    def get_holiday_rules(self, user: UserContext) -> dict[str, Any]:
        """调用 /api/attendance/getHolidayRuleByUser 获取假期类型。"""
        return self._post_crm_json(
            "attendance.getHolidayRuleByUser",
            self._holiday_rule_url,
            user,
            {},
        )

    def add_approval(
        self,
        user: UserContext,
        approval_set_id: str,
        node_list: list[dict[str, Any]],
        form_data: dict[str, Any],
    ) -> dict[str, Any]:
        """调用 /api/approval/add 创建审批。"""
        return self._post_crm_json(
            "approval.add",
            self._add_approval_url,
            user,
            {
                "approval_set_id": int(approval_set_id),
                "node_list": node_list,
                "form_data": form_data,
            },
        )

    def _post_crm_json(
        self,
        event: str,
        url: str,
        user: UserContext,
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """统一调用 CRM POST JSON 接口并记录请求、响应和耗时。"""
        headers = _crm_headers(user)
        started_at = self._clock()
        status_code: int | None = None
        try:
            self._log_crm_request(event, url, headers, body)
            response = self._http_client.post(url, headers=headers, json=body)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            self._log_crm_response(event, payload)
            self._log_crm_timing(event, url, started_at, self._clock(), True, status_code)
            return payload
        except Exception as exc:
            self._log_crm_timing(
                event,
                url,
                started_at,
                self._clock(),
                False,
                status_code,
                str(exc),
            )
            raise

    def _log_crm_request(
        self, event: str, url: str, headers: dict[str, str], body: dict[str, Any]
    ) -> None:
        """记录 CRM 请求，Authorization 会在日志服务中脱敏。"""
        self._log_writer(
            f"crm.{event}.request",
            {
                "url": url,
                "headers": headers,
                "body": body,
            },
        )

    def _log_crm_response(self, event: str, payload: dict[str, Any]) -> None:
        """记录 CRM 响应摘要，避免大响应刷爆日志。"""
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
        self._log_writer(f"crm.{event}.response", summary)

    def _log_crm_timing(
        self,
        event: str,
        url: str,
        started_at: float,
        finished_at: float,
        success: bool,
        status_code: int | None,
        error: str | None = None,
    ) -> None:
        """记录 CRM 接口耗时摘要。"""
        payload: dict[str, Any] = {
            "url": url,
            "duration_ms": max(0, int((finished_at - started_at) * 1000)),
            "success": success,
            "status_code": status_code,
        }
        if error:
            payload["error"] = error[:300]
        self._log_writer(f"crm.{event}.timing", payload)


def _crm_headers(user: UserContext) -> dict[str, str]:
    """构建 CRM 接口请求头。"""
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": user.authorization or "",
        "UID": user.uid or "",
    }

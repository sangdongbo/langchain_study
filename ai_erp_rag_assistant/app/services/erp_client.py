from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

import httpx

from ai_erp_rag_assistant.app.config import get_settings


class ErpClient:
    """ERP adapter.

    Remote mode calls the same approval endpoints used by ai_approval_assistant.
    Mock mode is intentionally explicit and only exists for offline rehearsal;
    its response carries ``erp_mode=mock`` so it cannot be mistaken for ERP data.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def mode(self) -> str:
        return self.settings.erp_mode.lower().strip()

    def _headers(self, user: dict[str, Any]) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": str(user.get("authorization") or self.settings.erp_authorization),
            "UID": str(user.get("uid") or self.settings.erp_uid),
        }

    def _post(self, path: str, body: dict[str, Any], user: dict[str, Any]) -> dict[str, Any]:
        url = f"{self.settings.erp_base_url.rstrip('/')}{path}"
        response = httpx.post(url, headers=self._headers(user), json=body, timeout=15)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, dict):
            raise RuntimeError(f"ERP 返回不是 JSON 对象：{path}")
        return payload

    def get_current_user(self, user_id: str, *, uid: str, authorization: str, company_id: str, department: str) -> dict[str, Any]:
        user = {
            "user_id": user_id,
            "uid": uid or self.settings.erp_uid,
            "authorization": authorization or self.settings.erp_authorization,
            "company_id": company_id,
            "department": department,
        }
        if self.mode == "mock":
            user.update({
                # Match the tenant metadata written by the bundled handbook.
                # Both values remain request/config overridable for other companies.
                "company_id": company_id or self.settings.erp_demo_company_id or "lanjing",
                "department": department or self.settings.erp_demo_department or "研发部",
                "roles": ["employee"],
                "permissions": ["approval:create", "knowledge:employee_handbook"],
                "erp_mode": "mock",
            })
            return user
        # Real ERP identity is obtained from credentials when available. The
        # user_id remains the caller-provided correlation id for the demo.
        if not user["uid"] or not user["authorization"]:
            raise RuntimeError("ERP_MODE=remote 时必须在请求或 .env 提供 uid 和 authorization。")
        payload = self._post(self.settings.erp_userinfo_path, {}, user)
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        user.update(data)
        user["erp_mode"] = "remote"
        return user

    def get_approval_template(self, keyword: str, *, company_id: str, user: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "mock":
            return {
                "template_code": "LEAVE_DYNAMIC_DEMO",
                "template_id": "demo-leave",
                "company_id": company_id,
                "fields": [
                    {"name": "leave_type", "label": "请假类型", "required": True},
                    {"name": "start_time", "label": "开始时间", "required": True},
                    {"name": "end_time", "label": "结束时间", "required": True},
                    {"name": "reason", "label": "请假原因", "required": True},
                ],
                "erp_mode": "mock",
            }
        payload = self._post(self.settings.erp_approval_list_path, {"keyword": keyword}, user)
        template = _first_approval(payload.get("data"))
        if not template:
            raise RuntimeError(f"ERP 未找到审批模板：{keyword}")
        template_id = str(template.get("id") or template.get("approval_set_id") or template.get("template_id") or "")
        fields_payload = self._post(self.settings.erp_form_fields_path, {"field_form": f"approval_type_{template_id}"}, user)
        fields = _normalize_fields(fields_payload.get("data") or [])
        return {
            "template_code": template_id,
            "template_id": template_id,
            "title": template.get("title") or template.get("name") or keyword,
            "company_id": company_id,
            "fields": fields,
            "erp_mode": "remote",
        }

    def query_approval_status(self, user_id: str, *, user: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "mock":
            return {
                "user_id": user_id,
                "approval_id": f"DEMO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "status": "演示模式：未连接 ERP",
                "current_assignee": "请配置 ERP 凭证后查询",
                "erp_mode": "mock",
            }
        payload = self._post(
            self.settings.erp_approval_status_path,
            {"user_id": user.get("user_id"), "page": 1, "pageSize": 10},
            user,
        )
        data = payload.get("data") or []
        items = data.get("list") if isinstance(data, dict) else data
        items = items if isinstance(items, list) else []
        return {"user_id": user_id, "items": items[:10], "erp_mode": "remote"}

    def submit_approval(self, preview: dict[str, Any], *, user: dict[str, Any]) -> dict[str, Any]:
        if self.mode == "mock":
            return {
                "approval_id": f"DEMO-{uuid4().hex[:12]}",
                "status": "演示模式：未写入 ERP",
                "template_code": preview.get("template_code"),
                "erp_mode": "mock",
            }
        template_id = str(preview.get("template_id") or preview.get("template_code") or "")
        if not template_id.isdigit():
            raise RuntimeError("ERP 提交需要远程 approval_set_id，当前模板没有返回数字 ID。")
        form_value = [
            {"field_key": str(key), "value": value}
            for key, value in (preview.get("fields") or {}).items()
        ]
        nodes = preview.get("nodes") or []
        if not nodes:
            node_payload = self._post(
                self.settings.erp_get_nodes_path,
                {"approval_set_id": int(template_id), "form_value": form_value},
                user,
            )
            nodes = node_payload.get("data") if isinstance(node_payload.get("data"), list) else []
        payload = self._post(
            self.settings.erp_add_approval_path,
            {
                "approval_set_id": int(template_id),
                "node_list": nodes,
                "form_data": _remote_form_data(preview.get("fields") or {}),
            },
            user,
        )
        return {"data": payload.get("data"), "message": payload.get("message"), "erp_mode": "remote", "nodes": nodes}


def _first_approval(data: Any) -> dict[str, Any] | None:
    """Flatten the grouped payload returned by ERP approval/list."""
    if isinstance(data, dict):
        for key in ("approvals", "list", "data", "items"):
            found = _first_approval(data.get(key))
            if found:
                return found
        return data if data.get("id") or data.get("approval_set_id") else None
    if isinstance(data, list):
        for item in data:
            found = _first_approval(item)
            if found:
                return found
    return None


def _normalize_fields(data: Any) -> list[dict[str, Any]]:
    """Normalize common ERP field payload variants into an agent-facing schema."""
    if isinstance(data, dict):
        for key in ("fields", "list", "data", "items", "children"):
            found = _normalize_fields(data.get(key))
            if found:
                return found
        return []
    if not isinstance(data, list):
        return []
    normalized: list[dict[str, Any]] = []
    for item in data:
        if not isinstance(item, dict):
            continue
        children = item.get("children") or item.get("fields")
        if children:
            normalized.extend(_normalize_fields(children))
            continue
        name = str(item.get("name") or item.get("field_key") or item.get("field_id") or "").strip()
        label = str(item.get("label") or item.get("field_name") or item.get("title") or name).strip()
        if not name:
            continue
        raw_required = item.get("required", item.get("is_required", item.get("isRequired", False)))
        required = raw_required in (True, 1, "1", "true", "True")
        options = item.get("options") or item.get("option_values") or item.get("values") or []
        normalized_options = []
        for option in options if isinstance(options, list) else []:
            if isinstance(option, dict):
                normalized_options.append(option.get("label") or option.get("name") or option.get("value"))
            else:
                normalized_options.append(option)
        normalized.append({
            "name": name,
            "label": label,
            "required": required,
            "type": item.get("type") or item.get("field_type") or "text",
            "options": [str(option) for option in normalized_options if option is not None],
        })
    return normalized


def _remote_form_data(fields: dict[str, Any]) -> dict[str, Any]:
    """Match ERP approval/add's field-value envelope used by the main assistant."""
    result: dict[str, Any] = {}
    for key, value in fields.items():
        result[str(key)] = value if isinstance(value, (dict, list)) else {"value": value}
    return result


erp_client = ErpClient()

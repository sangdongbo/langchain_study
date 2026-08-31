from __future__ import annotations

import logging
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from time import monotonic
from typing import Any
from uuid import uuid4

import httpx

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.services.approval_form_service import (
    find_field,
    normalize_approval_nodes,
    normalize_erp_fields,
    project_chat_fields,
)
from ai_erp_rag_assistant.app.services.audit_log_service import (
    summarize_response,
    write_audit_event,
)


logger = logging.getLogger("ai_erp_rag_assistant.erp")


# Form values such as "病假" describe a leave subtype, not the name of an
# approval template.  Keep this vocabulary at the adapter boundary so every
# caller searches the dynamic ERP catalogue with the same business semantics.
_APPROVAL_TYPE_ALIASES: dict[str, tuple[str, ...]] = {
    "请假": (
        "请假", "休假", "病假", "事假", "年假", "调休", "婚假", "产假",
        "陪产假", "丧假", "哺乳假", "育儿假",
    ),
    "报销": ("报销", "费用报销", "差旅费", "发票报销"),
    "采购": ("采购", "购买", "申购"),
    "用章": ("用章", "盖章", "印章"),
    "外出": ("外出",),
    "出差": ("出差", "差旅申请"),
    "加班": ("加班",),
    "入库": ("入库",),
    "出库": ("出库",),
}

_GENERIC_APPROVAL_WORDS = (
    "麻烦", "帮我", "我要", "我想", "需要", "请帮忙", "发起", "办理",
    "提交", "审批", "申请", "流程", "一个", "一下",
)


class ErpClient:
    """ERP adapter.

    Remote mode calls the same approval endpoints used by ai_approval_assistant.
    Mock mode is intentionally explicit and only exists for offline rehearsal;
    its response carries ``erp_mode=mock`` so it cannot be mistaken for ERP data.
    """

    def __init__(self) -> None:
        self.settings = get_settings()

    @property
    def read_mode(self) -> str:
        return (self.settings.erp_read_mode or self.settings.erp_mode).lower().strip()

    @property
    def write_mode(self) -> str:
        return self.settings.erp_write_mode.lower().strip()

    def _headers(self, user: dict[str, Any]) -> dict[str, str]:
        return {
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Authorization": str(user.get("authorization") or self.settings.erp_authorization),
            "UID": str(user.get("uid") or self.settings.erp_uid),
        }

    def _post(
        self,
        path: str,
        body: dict[str, Any],
        user: dict[str, Any],
        *,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        url = f"{self.settings.erp_base_url.rstrip('/')}{path}"
        headers = self._headers(user)
        headers.update(extra_headers or {})
        request_id = uuid4().hex
        started_at = monotonic()
        status_code: int | None = None
        write_audit_event(
            "erp.request",
            {
                "request_id": request_id,
                "path": path,
                "company_id": user.get("company_id"),
                "user_id": user.get("user_id"),
                "uid": user.get("uid"),
                "body": body,
            },
        )
        try:
            response = httpx.post(url, headers=headers, json=body, timeout=15)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise RuntimeError(f"ERP 返回不是 JSON 对象：{path}")
            write_audit_event(
                "erp.response",
                {
                    "request_id": request_id,
                    "path": path,
                    "status_code": status_code,
                    **summarize_response(payload),
                },
            )
            return payload
        except Exception as exc:
            write_audit_event(
                "erp.error",
                {
                    "request_id": request_id,
                    "path": path,
                    "status_code": status_code,
                    "error_type": type(exc).__name__,
                    "error": str(exc)[:300],
                },
            )
            raise
        finally:
            write_audit_event(
                "erp.timing",
                {
                    "request_id": request_id,
                    "path": path,
                    "status_code": status_code,
                    "duration_ms": max(0, int((monotonic() - started_at) * 1000)),
                },
            )

    def get_current_user(self, user_id: str, *, uid: str, authorization: str, company_id: str, department: str) -> dict[str, Any]:
        user = {
            "user_id": user_id,
            "uid": uid or self.settings.erp_uid,
            "authorization": authorization or self.settings.erp_authorization,
            "company_id": company_id,
            "department": department,
        }
        if self.read_mode == "mock":
            user.update({
                # Match the tenant metadata written by the bundled handbook.
                # Both values remain request/config overridable for other companies.
                "company_id": company_id or self.settings.erp_demo_company_id or "lanjing",
                "department": department or self.settings.erp_demo_department or "研发部",
                "roles": ["employee"],
                "permissions": ["approval:create", "knowledge:employee_handbook"],
                "erp_mode": "mock",
                "erp_write_mode": self.write_mode,
            })
            return user
        # Real ERP identity is obtained from credentials when available. The
        # user_id remains the caller-provided correlation id for the demo.
        if not user["uid"] or not user["authorization"]:
            if not self.settings.erp_skip_userinfo_validation:
                raise RuntimeError("ERP_MODE=remote 时必须在请求或 .env 提供 uid 和 authorization。")
        if self.settings.erp_skip_userinfo_validation:
            # Demo-only fallback: keep the caller credentials for later real
            # ERP calls, but skip /userinfo so an expired token cannot block
            # public knowledge-base questions. This is never a write path.
            user.update({
                "company_id": company_id or self.settings.erp_demo_company_id or self.settings.rag_company_id,
                "department": department or self.settings.erp_demo_department or self.settings.rag_department,
                "roles": ["employee"],
                "permissions": ["approval:create", *self.settings.rag_permission_tags],
                "erp_mode": "remote",
                "erp_write_mode": self.write_mode,
                "erp_auth_verified": False,
                "erp_identity_source": "demo_fallback",
            })
            logger.warning("ERP userinfo validation skipped by ERP_SKIP_USERINFO_VALIDATION; demo identity only.")
            return user
        payload = self._post(self.settings.erp_userinfo_path, {}, user)
        _require_success(payload, "用户信息")
        raw_data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        data = raw_data.get("user") if isinstance(raw_data.get("user"), dict) else raw_data
        user.update(data)
        user["company_id"] = str(
            _scalar(data.get("company_id"))
            or data.get("companyId")
            or data.get("company_code")
            or company_id
            or ""
        )
        user["department"] = str(
            data.get("department")
            or data.get("department_name")
            or data.get("departmentName")
            or department
            or ""
        )
        user["permissions"] = _string_list(
            data.get("permissions")
            or data.get("permission_tags")
            or data.get("permissionTags")
            or []
        )
        user["erp_mode"] = "remote"
        user["erp_write_mode"] = self.write_mode
        user["raw_userinfo"] = raw_data
        return user

    def list_approval_templates(self, query: str, *, company_id: str, user: dict[str, Any]) -> list[dict[str, Any]]:
        if self.read_mode == "mock":
            catalog = [
                {"template_id": "demo-leave", "title": "请假申请", "description": "员工请假：事假、病假、年假", "company_id": company_id},
                {"template_id": "demo-expense", "title": "费用报销", "description": "费用报销、发票、餐饮费", "company_id": company_id},
                {"template_id": "demo-purchase", "title": "采购申请", "description": "采购物品、购买、预算", "company_id": company_id},
                {"template_id": "demo-seal", "title": "合同用章", "description": "合同盖章、公章、合同章", "company_id": company_id},
            ]
            return _filter_relevant_templates(query, catalog)
        queries = [query.strip()]
        queries.extend(_approval_search_keywords(query))
        for search_query in dict.fromkeys(queries):
            payload = self._post(self.settings.erp_approval_list_path, {"keyword": search_query}, user)
            _require_success(payload, "审批模板列表")
            templates = [_normalize_template_summary(item, company_id) for item in _approval_items(payload.get("data"))]
            relevant = _filter_relevant_templates(query, templates)
            if relevant:
                return relevant
        # A non-empty, specific request must never fall back to the complete
        # catalogue.  Some ERP deployments ignore `keyword`; returning that
        # response would make unrelated templates candidates for the LLM.
        return []

    def get_approval_template(self, template_id: str, *, company_id: str, title: str = "", user: dict[str, Any]) -> dict[str, Any]:
        if self.read_mode == "mock":
            templates = {
                "demo-leave": {
                    "fields": [
                        {"name": "leave_category", "label": "请假类型", "type": "select", "options": ["事假", "病假", "年假"], "required": True},
                        {"name": "begin_at", "label": "开始时间", "type": "datetime", "required": True},
                        {"name": "finish_at", "label": "结束时间", "type": "datetime", "required": True},
                        {"name": "leave_reason", "label": "请假原因", "type": "textarea", "required": True},
                    ]
                },
                "demo-expense": {
                    "fields": [
                        {"name": "expense_category", "label": "费用类型", "type": "select", "options": ["办公用品", "差旅", "招待"], "required": True},
                        {"name": "total_amount", "label": "报销金额", "type": "number", "required": True},
                        {"name": "expense_description", "label": "费用说明", "type": "textarea", "required": True},
                        {"name": "invoice_attachment", "label": "发票附件", "type": "attachment", "required": True},
                    ]
                },
                "demo-purchase": {
                    "fields": [
                        {"name": "item_name", "label": "物品名称", "type": "text", "required": True},
                        {"name": "quantity", "label": "数量", "type": "number", "required": True},
                        {"name": "budget", "label": "预算", "type": "number", "required": True},
                        {"name": "purchase_reason", "label": "采购原因", "type": "textarea", "required": True},
                    ]
                },
                "demo-seal": {
                    "fields": [
                        {"name": "contract_name", "label": "合同名称", "type": "text", "required": True},
                        {"name": "seal_type", "label": "印章类型", "type": "select", "options": ["公章", "合同章"], "required": True},
                        {"name": "copy_count", "label": "用章份数", "type": "number", "required": True},
                    ]
                },
            }
            template = templates.get(template_id)
            if not template:
                raise RuntimeError(f"演示 ERP 未找到模板：{template_id}")
            return {
                "template_code": template_id,
                "template_id": template_id,
                "title": title or template_id,
                "company_id": company_id,
                "fields": template["fields"],
                "erp_mode": "mock",
                "erp_write_mode": self.write_mode,
            }
        fields_payload = self._post(self.settings.erp_form_fields_path, {"field_form": f"approval_type_{template_id}"}, user)
        _require_success(fields_payload, "审批表单字段")
        form_fields = normalize_erp_fields(fields_payload.get("data") or [])
        self._enrich_dynamic_fields(form_fields, user)
        fields = project_chat_fields(form_fields)
        return {
            "template_code": template_id,
            "template_id": template_id,
            "title": title or template_id,
            "company_id": company_id,
            "fields": fields,
            "all_fields": form_fields,
            "form_schema": {
                "schema_version": "1.0",
                "template": {
                    "template_id": str(template_id),
                    "template_code": str(template_id),
                    "title": title or template_id,
                    "company_id": company_id,
                },
                "fields": deepcopy(form_fields),
                "values": {},
                "missing_field_keys": [],
                "invalid_fields": [],
            },
            "erp_mode": "remote",
            "erp_write_mode": self.write_mode,
        }

    def query_approval_status(self, user_id: str, *, user: dict[str, Any]) -> dict[str, Any]:
        if self.read_mode == "mock":
            return {
                "user_id": user_id,
                "approval_id": f"DEMO-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
                "status": "演示模式：未连接 ERP",
                "current_assignee": "请配置 ERP 凭证后查询",
                "erp_mode": "mock",
                "erp_write_mode": self.write_mode,
            }
        payload = self._post(
            self.settings.erp_approval_status_path,
            {"user_id": user.get("user_id"), "page": 1, "pageSize": 10},
            user,
        )
        _require_success(payload, "审批状态")
        data = payload.get("data") or []
        items = data.get("list") if isinstance(data, dict) else data
        items = items if isinstance(items, list) else []
        return {"user_id": user_id, "items": items[:10], "erp_mode": "remote", "erp_write_mode": self.write_mode}

    def get_approval_nodes(
        self,
        template_id: str,
        fields: dict[str, Any],
        *,
        user: dict[str, Any],
    ) -> list[dict[str, Any]]:
        """Read the real approval route before preview; this endpoint is non-writing."""
        if self.read_mode == "mock" or not str(template_id).isdigit():
            return []
        form_value = [
            {"field_key": str(key), "value": _structured_value(value)}
            for key, value in fields.items()
        ]
        payload = self._post(
            self.settings.erp_get_nodes_path,
            {"approval_set_id": int(template_id), "form_value": form_value},
            user,
        )
        _require_success(payload, "审批节点")
        data = payload.get("data")
        nodes = data if isinstance(data, list) else []
        self._enrich_unrestricted_node_candidates(nodes, user)
        return nodes

    def _enrich_dynamic_fields(self, fields: list[dict[str, Any]], user: dict[str, Any]) -> None:
        """Load options ERP exposes through a separate endpoint."""
        holiday_field = find_field(fields, "rest_holiday_rule_id")
        if not holiday_field or self.read_mode == "mock":
            return
        option_values = [_holiday_rule_option(item) for item in self.get_holiday_rules(user)]
        option_values = [option for option in option_values if option]
        holiday_field["option_values"] = option_values
        holiday_field["options"] = [str(option["label"]) for option in option_values]
        holiday_field["option_source"] = {
            "type": "holiday_rule",
            "lazy": False,
            "searchable": False,
        }

    def get_field_options(
        self,
        template_id: str,
        field_key: str,
        *,
        company_id: str,
        user: dict[str, Any],
        title: str = "",
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> dict[str, Any]:
        """Resolve static or remote options for one dynamic ERP field."""
        template = self.get_approval_template(
            template_id,
            company_id=company_id,
            title=title,
            user=user,
        )
        field_definitions = template.get("all_fields") or template.get("fields") or []
        if field_definitions and not any(
            isinstance(item, dict) and item.get("component") for item in field_definitions
        ):
            field_definitions = normalize_erp_fields(field_definitions)
        field = find_field(field_definitions, field_key)
        if not field:
            raise RuntimeError(f"审批模板中不存在字段：{field_key}")
        source = field.get("option_source") if isinstance(field.get("option_source"), dict) else {}
        source_type = str(source.get("type") or "")
        options = list(field.get("option_values") or [])
        if not options:
            options = [
                {"label": str(option), "value": option, "disabled": False, "meta": {}}
                for option in field.get("options", [])
                if option not in (None, "")
            ]
        total: int | None = len(options)
        if source_type == "related_list":
            items, total = self.get_related_list(
                str(source.get("relate_type") or ""),
                user=user,
                keyword=keyword,
                page=page,
                page_size=page_size,
            )
            options = [_related_item_option(item) for item in items]
        elif source_type == "user_list":
            items = self.get_user_list(user, keyword=keyword, page_size=page_size)
            options = [_user_option(item) for item in items]
            total = len(options)
        options = [option for option in options if option]
        if keyword and source_type in {"", "static", "holiday_rule"}:
            marker = keyword.lower().strip()
            options = [option for option in options if marker in str(option.get("label") or "").lower()]
            total = len(options)
        return {
            "template_id": str(template_id),
            "field_key": str(field_key),
            "source": source or {"type": "static", "lazy": False, "searchable": False},
            "options": options,
            "page": page,
            "page_size": page_size,
            "total": total,
            "has_more": bool(total is not None and page * page_size < total),
        }

    def get_related_list(
        self,
        relate_type: str,
        *,
        user: dict[str, Any],
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int | None]:
        payload = self._post(
            self.settings.erp_related_list_path,
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
            user,
        )
        _require_success(payload, "关联字段选项")
        data = payload.get("data")
        if isinstance(data, dict):
            items = data.get("data") or data.get("list") or data.get("items") or []
            total_value = data.get("total") or data.get("count")
            total = int(total_value) if str(total_value or "").isdigit() else None
        else:
            items, total = data or [], None
        return [item for item in items if isinstance(item, dict)], total

    def get_holiday_rules(self, user: dict[str, Any]) -> list[dict[str, Any]]:
        payload = self._post(self.settings.erp_holiday_rule_path, {}, user)
        _require_success(payload, "假期类型")
        data = payload.get("data")
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def get_user_list(
        self,
        user: dict[str, Any],
        *,
        keyword: str = "",
        page_size: int = 2000,
    ) -> list[dict[str, Any]]:
        payload = self._post(
            self.settings.erp_user_list_path,
            {"keyword": keyword, "pageSize": page_size},
            user,
        )
        _require_success(payload, "可选人员")
        data = payload.get("data")
        if isinstance(data, dict):
            data = data.get("data") or data.get("list") or data.get("items") or []
        return [item for item in data if isinstance(item, dict)] if isinstance(data, list) else []

    def _enrich_unrestricted_node_candidates(
        self,
        nodes: list[dict[str, Any]],
        user: dict[str, Any],
    ) -> None:
        normalized = normalize_approval_nodes(nodes)
        needs_users = any(
            node.get("requires_selection") and not node.get("candidates")
            for node in normalized
        )
        if not needs_users:
            return
        users = self.get_user_list(user)
        for node in nodes:
            handle = _node_handle(node.get("handle"))
            if str(handle.get("type") or "") == "submitter_choice" and not _node_candidate_items(handle):
                handle["relate_user"] = users

    def submit_approval(self, preview: dict[str, Any], *, user: dict[str, Any]) -> dict[str, Any]:
        if self.write_mode == "disabled":
            return {
                "status": "演示模式：已阻止写入 ERP，仅生成预览",
                "template_code": preview.get("template_code"),
                "idempotency_key": preview.get("idempotency_key"),
                "erp_mode": user.get("erp_mode") or self.read_mode,
                "erp_write_mode": "disabled",
            }
        if self.write_mode == "mock":
            return {
                "approval_id": f"DEMO-{uuid4().hex[:12]}",
                "status": "演示模式：未写入 ERP",
                "template_code": preview.get("template_code"),
                "idempotency_key": preview.get("idempotency_key"),
                "erp_mode": "mock",
                "erp_write_mode": "mock",
            }
        template_id = str(preview.get("template_id") or preview.get("template_code") or "")
        if not template_id.isdigit():
            raise RuntimeError("ERP 提交需要远程 approval_set_id，当前模板没有返回数字 ID。")
        submission_fields = preview.get("submission_fields") or preview.get("fields") or {}
        form_value = [
            {"field_key": str(key), "value": _structured_value(value)}
            for key, value in submission_fields.items()
        ]
        nodes = preview.get("submit_nodes") or preview.get("nodes") or []
        if not nodes:
            node_payload = self._post(
                self.settings.erp_get_nodes_path,
                {"approval_set_id": int(template_id), "form_value": form_value},
                user,
            )
            _require_success(node_payload, "审批节点")
            nodes = node_payload.get("data") if isinstance(node_payload.get("data"), list) else []
        idempotency_key = str(preview.get("idempotency_key") or uuid4().hex)
        form_data = self._remote_submission_form_data(submission_fields, user)
        payload = self._post(
            self.settings.erp_add_approval_path,
            {
                "approval_set_id": int(template_id),
                "node_list": nodes,
                "form_data": form_data,
            },
            user,
            extra_headers={"Idempotency-Key": idempotency_key},
        )
        _require_success(payload, "创建审批")
        data = payload.get("data")
        approval_id = ""
        if isinstance(data, dict):
            approval_id = str(data.get("id") or data.get("approval_id") or data.get("approvalId") or "")
        logger.info(
            "ERP approval submitted",
            extra={
                "approval_id": approval_id,
                "template_id": template_id,
                "idempotency_key": idempotency_key,
                "user_id": user.get("user_id"),
                "company_id": user.get("company_id"),
            },
        )
        return {
            "approval_id": approval_id,
            "data": data,
            "message": payload.get("message"),
            "erp_mode": "remote",
            "erp_write_mode": "remote",
            "nodes": nodes,
            "idempotency_key": idempotency_key,
        }

    def _remote_submission_form_data(
        self,
        fields: dict[str, Any],
        user: dict[str, Any],
    ) -> dict[str, Any]:
        """Add ERP-derived leave control values before the real write call."""
        form_data = _remote_form_data(fields)
        holiday_rule_id = _structured_value(form_data.get("rest_holiday_rule_id"))
        start_date = _structured_value(form_data.get("rest_start_time"))
        end_date = _structured_value(form_data.get("rest_end_time"))
        if holiday_rule_id is None or not start_date or not end_date:
            return form_data
        selected_rule = next(
            (
                item
                for item in self.get_holiday_rules(user)
                if str(item.get("id")) == str(holiday_rule_id)
            ),
            None,
        )
        if not selected_rule:
            raise RuntimeError("ERP 未找到所选假期规则，不能提交请假审批。")
        start_text, end_text = _normalize_leave_time_fields(
            form_data,
            selected_rule,
            str(start_date),
            str(end_date),
        )
        duration_payload = self._post(
            self.settings.erp_calculate_holiday_duration_path,
            {
                "attendance_holiday_config_id": int(holiday_rule_id),
                "start_date": start_text,
                "end_date": end_text,
            },
            user,
        )
        _require_success(duration_payload, "请假时长计算")
        duration_data = duration_payload.get("data") if isinstance(duration_payload.get("data"), dict) else {}
        rest_rule_json = deepcopy(selected_rule)
        rest_rule_json["holiday_day_list"] = duration_data.get("holiday_day_list") or []
        rest_rule_json["web_show_day_list"] = duration_data.get("web_show_day_list") or []
        form_data["rest_rule_json"] = rest_rule_json
        if duration_data.get("all_duration") is not None:
            duration = duration_data["all_duration"]
            form_data["rest_duration"] = {"label": str(duration), "value": duration}
        form_data.setdefault("rest_prove", [])
        return form_data


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


def _require_success(payload: dict[str, Any], label: str) -> None:
    code = payload.get("code")
    if code not in (None, 200):
        raise RuntimeError(f"ERP {label}接口返回错误：{code} {payload.get('message') or ''}".strip())


def _scalar(value: Any) -> Any:
    if isinstance(value, dict):
        return value.get("value") or value.get("id") or value.get("name")
    if isinstance(value, list):
        return value[0] if value else None
    return value


def _approval_items(data: Any, parent: dict[str, str] | None = None) -> list[dict[str, Any]]:
    """Flatten the grouped payload returned by /api/approval/list."""
    if isinstance(data, dict):
        context = dict(parent or {})
        child_keys = ("approvals", "list", "data", "items", "groups", "children", "_child")
        has_children = any(isinstance(data.get(key), (dict, list)) for key in child_keys)
        if has_children:
            group_name = str(
                data.get("group_name")
                or data.get("category")
                or data.get("group_title")
                or data.get("name")
                or ""
            ).strip()
            if group_name:
                context["group_name"] = group_name
                context["category"] = str(data.get("category") or group_name).strip()
            template_type = str(
                data.get("template_type")
                or data.get("business_type")
                or data.get("approval_type")
                or ""
            ).strip()
            if template_type:
                context["template_type"] = template_type
        if not has_children and (data.get("id") or data.get("approval_set_id") or data.get("template_id")):
            item = dict(data)
            for key, value in context.items():
                if value and not item.get(key):
                    item[key] = value
            return [item]
        items: list[dict[str, Any]] = []
        for key in child_keys:
            items.extend(_approval_items(data.get(key), context))
        return items
    if isinstance(data, list):
        items: list[dict[str, Any]] = []
        for item in data:
            items.extend(_approval_items(item, parent))
        return items
    return []


def _normalize_template_summary(item: dict[str, Any], company_id: str) -> dict[str, Any]:
    template_id = str(item.get("id") or item.get("approval_set_id") or item.get("template_id") or "").strip()
    title = str(item.get("name") or item.get("title") or item.get("approval_name") or template_id).strip()
    group_name = str(item.get("group_name") or item.get("category") or "").strip()
    return {
        "template_id": template_id,
        "title": title,
        "description": str(item.get("description") or item.get("remark") or "").strip(),
        "category": str(item.get("category") or group_name).strip(),
        "group_name": group_name,
        "template_type": str(
            item.get("template_type")
            or item.get("business_type")
            or item.get("approval_type")
            or item.get("type")
            or ""
        ).strip(),
        "company_id": company_id,
    }


def _approval_search_keywords(keyword: str) -> list[str]:
    result: list[str] = []
    for approval_type in _approval_types(keyword):
        result.append(approval_type)
        result.extend(
            alias
            for alias in _APPROVAL_TYPE_ALIASES[approval_type]
            if alias in keyword
        )
    if not result:
        result.extend(_query_business_terms(keyword))
    return list(dict.fromkeys(result))


def _approval_types(text: str) -> list[str]:
    """Map field-level words such as 病假 to their approval business type."""
    normalized = _compact_text(text)
    return [
        approval_type
        for approval_type, aliases in _APPROVAL_TYPE_ALIASES.items()
        if any(_compact_text(alias) in normalized for alias in aliases)
    ]


def _filter_relevant_templates(query: str, templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep only templates that are deterministically related to the request.

    ERP remains the source of truth for template IDs and dynamic fields.  This
    function only guards against an ERP list endpoint that returns the entire
    catalogue even when a keyword was supplied.
    """
    if not templates:
        return []
    if not query.strip() or _is_vague_approval_query(query):
        return _deduplicate_templates(templates)

    scored = [
        (_template_match_score(query, template), index, template)
        for index, template in enumerate(templates)
    ]
    relevant = [item for item in scored if item[0] > 0]
    relevant.sort(key=lambda item: (-item[0], item[1]))
    return _deduplicate_templates([item[2] for item in relevant])


def _template_match_score(query: str, template: dict[str, Any]) -> int:
    approval_types = _approval_types(query)
    title = _compact_text(template.get("title"))
    description = _compact_text(template.get("description"))
    structural_values = [
        _compact_text(template.get("template_type")),
        _compact_text(template.get("category")),
        _compact_text(template.get("group_name")),
    ]
    if approval_types:
        score = 0
        for approval_type in approval_types:
            aliases = _APPROVAL_TYPE_ALIASES[approval_type]
            canonical = _compact_text(approval_type)
            if canonical and canonical in title:
                score = max(score, 120)
            elif any(_compact_text(alias) in title for alias in aliases):
                score = max(score, 110)
            if any(
                marker and marker in value
                for value in structural_values
                for marker in (canonical, *(_compact_text(alias) for alias in aliases))
            ):
                score = max(score, 100)
            if any(_compact_text(alias) in description for alias in aliases):
                score = max(score, 40)
        return score

    terms = _query_business_terms(query)
    score = 0
    for term in terms:
        normalized_term = _compact_text(term)
        if not normalized_term:
            continue
        if normalized_term in title or title in normalized_term:
            score = max(score, 100)
        elif any(
            value and (normalized_term in value or value in normalized_term)
            for value in structural_values
        ):
            score = max(score, 80)
        elif normalized_term in description:
            score = max(score, 30)
    return score


def _query_business_terms(query: str) -> list[str]:
    cleaned = _compact_text(query)
    for word in _GENERIC_APPROVAL_WORDS:
        cleaned = cleaned.replace(_compact_text(word), "")
    return [cleaned] if len(cleaned) >= 2 else []


def _is_vague_approval_query(query: str) -> bool:
    return not _approval_types(query) and not _query_business_terms(query)


def _deduplicate_templates(templates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[str] = set()
    for template in templates:
        identity = str(template.get("template_id") or "").strip()
        if not identity or identity in seen:
            continue
        seen.add(identity)
        result.append(template)
    return result


def _compact_text(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def _normalize_fields(data: Any) -> list[dict[str, Any]]:
    """Backward-compatible compact field projection for existing callers."""
    result: list[dict[str, Any]] = []
    for field in normalize_erp_fields(data):
        if not field.get("required"):
            continue
        result.append(
            {
                "name": field["name"],
                "label": field["label"],
                "required": True,
                "type": field["type"],
                "erp_field_type": field["erp_field_type"],
                "options": field.get("options", []),
                "option_values": [
                    {"label": option.get("label"), "value": option.get("value")}
                    for option in field.get("option_values", [])
                ],
                "input_type": field.get("input_type") or "",
            }
        )
    return result


def _remote_form_data(fields: dict[str, Any]) -> dict[str, Any]:
    """Match ERP approval/add's field-value envelope used by the main assistant."""
    result: dict[str, Any] = {}
    for key, value in fields.items():
        result[str(key)] = value if isinstance(value, (dict, list)) else {"value": value}
    return result


def _structured_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _holiday_rule_option(item: dict[str, Any]) -> dict[str, Any] | None:
    rule_id = item.get("id")
    name = str(item.get("name") or item.get("title") or item.get("label") or "").strip()
    if rule_id is None or not name:
        return None
    unit = "小时" if item.get("time_unit") == "hour" else "天"
    if int(item.get("balance_rule") or 0) == 1:
        label = f"{name}（余{item.get('balance') or 0}{unit}）"
    else:
        rule = item.get("json_rule") if isinstance(item.get("json_rule"), dict) else {}
        if int(rule.get("is_continuous_holidays") or 0) == 1:
            label = f"{name}（{rule.get('continuous_holidays_day') or 0}{unit}）"
        else:
            label = name
    return {
        "label": label,
        "value": rule_id,
        "disabled": False,
        "meta": {"time_unit": item.get("time_unit")},
    }


def _related_item_option(item: dict[str, Any]) -> dict[str, Any] | None:
    label = ""
    for key in ("order_num", "name", "title", "num", "no", "id"):
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("text") or value.get("value") or value.get("name")
        if str(value or "").strip():
            label = str(value).strip()
            break
    if not label:
        return None
    value = item.get("id") or item.get("value") or label
    return {"label": label, "value": value, "disabled": False, "meta": {}}


def _user_option(item: dict[str, Any]) -> dict[str, Any] | None:
    uid = item.get("uid") or item.get("id")
    name = str(item.get("display_name") or item.get("name") or "").strip()
    if uid is None or not name:
        return None
    return {
        "label": name,
        "value": uid,
        "disabled": False,
        "meta": {"avatar": item.get("avatar")},
    }


def _node_handle(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        handles = [item for item in value if isinstance(item, dict)]
        return next(
            (item for item in handles if str(item.get("type") or "") == "submitter_choice"),
            handles[0] if handles else {},
        )
    return {}


def _node_candidate_items(handle: dict[str, Any]) -> list[Any]:
    items = handle.get("relate_id") if int(handle.get("is_all_company") or 0) == 2 else handle.get("relate_user")
    return items if isinstance(items, list) else []


def _normalize_leave_time_fields(
    form_data: dict[str, Any],
    holiday_rule: dict[str, Any],
    start_date: str,
    end_date: str,
) -> tuple[str, str]:
    if str(holiday_rule.get("time_unit") or "") != "day":
        return start_date, end_date
    start_day = start_date[:10]
    end_day = end_date[:10]
    next_end_day = (
        datetime.strptime(end_day, "%Y-%m-%d") + timedelta(days=1)
    ).strftime("%Y-%m-%d")
    form_data["rest_start_time"] = {
        "label": start_day,
        "value": start_day,
        "text": start_day,
        "time_unit": "05:00",
        "real_date": start_day,
    }
    form_data["rest_end_time"] = {
        "label": end_day,
        "value": end_day,
        "text": end_day,
        "time_unit": "05:00",
        "real_date": next_end_day,
    }
    return start_day, end_day


def _string_list(value: Any) -> list[str]:
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    if isinstance(value, dict):
        return [str(key) for key, enabled in value.items() if enabled]
    if isinstance(value, (list, tuple, set)):
        result: list[str] = []
        for item in value:
            if isinstance(item, dict):
                normalized = item.get("code") or item.get("name") or item.get("permission") or item.get("value")
                if normalized:
                    result.append(str(normalized))
            elif item is not None:
                result.append(str(item))
        return result
    return []


erp_client = ErpClient()

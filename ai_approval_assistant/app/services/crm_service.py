from __future__ import annotations
from copy import deepcopy
from datetime import datetime
import logging
import os
import time
from typing import Any
import httpx
from app.mock_data.approval_templates import (
    APPROVAL_TEMPLATES,
    USERS,
)
from app.schemas.approval import (
    ApprovalAssignee,
    ApprovalNode,
    ApprovalTemplate,
    FieldError,
    SubmitResult,
    UserContext,
    ValidationResult,
)
from app.services.crm_config_service import (
    load_crm_endpoint_config,
)
from app.services.debug_log_service import write_debug_log

logger = logging.getLogger("ai_approval_assistant.crm")

DYNAMIC_OPTION_FIELD_SOURCES = {
    "rest_holiday_rule_id": "holiday_rule",
}

DEFAULT_TEMPLATE_CACHE_TTL_SECONDS = 300
DEFAULT_DYNAMIC_OPTIONS_CACHE_TTL_SECONDS = 300


class CrmApprovalService:
    """CRM 适配器边界。

    当前实现同时支持本地模拟数据和 ERP HTTP 调用；后续替换真实 CRM 能力时，
    应优先修改本类方法，避免影响图工作流和 API 层。
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
        cache_ttl_seconds: int | None = None,
        dynamic_options_cache_ttl_seconds: int | None = None,
        clock: Any | None = None,
    ) -> None:
        """初始化 CRM 适配器地址、HTTP 客户端和模拟提交缓存。"""
        self._submitted_by_key: dict[str, SubmitResult] = {}
        self._remote_template_by_user_type: dict[tuple[str, str], dict[str, Any]] = {}
        self._remote_template_detail_by_user_type: dict[tuple[str, str], dict[str, Any]] = {}
        self._dynamic_options_cache: dict[tuple[Any, ...], dict[str, Any]] = {}
        self._template_cache_ttl_seconds = (
            cache_ttl_seconds
            if cache_ttl_seconds is not None
            else _template_cache_ttl_from_env()
        )
        self._dynamic_options_cache_ttl_seconds = (
            dynamic_options_cache_ttl_seconds
            if dynamic_options_cache_ttl_seconds is not None
            else _dynamic_options_cache_ttl_from_env()
        )
        self._clock = clock or time.monotonic
        self._http_client = http_client or httpx.Client(timeout=10)
        endpoint_config = load_crm_endpoint_config()
        self._approval_list_url = approval_list_url or endpoint_config.approval_list_url
        self._form_fields_url = form_fields_url or endpoint_config.form_fields_url
        self._get_nodes_url = get_nodes_url or endpoint_config.get_nodes_url
        self._add_approval_url = add_approval_url or endpoint_config.add_approval_url
        self._related_list_url = related_list_url or endpoint_config.related_list_url
        self._holiday_rule_url = holiday_rule_url or endpoint_config.holiday_rule_url

    def get_user_context(
        self, user_id: str, uid: str | None = None, authorization: str | None = None
    ) -> UserContext:
        """根据模拟数据和可选 ERP 凭证构建用户上下文。"""
        user = USERS.get(user_id)
        if user is None:
            user = {
                "user_id": user_id,
                "name": f"User {user_id}",
                "company_id": "",
                "dept_id": "",
                "role": "",
                "manager_id": "",
            }
        return UserContext(**user, uid=uid, authorization=authorization)

    def list_available_templates(self, user: UserContext) -> list[ApprovalTemplate]:
        """有授权时从 ERP 获取审批模板，否则返回本地模拟模板。"""
        return self.search_available_templates(user, "")

    def search_available_templates(
        self, user: UserContext, keyword: str
    ) -> list[ApprovalTemplate]:
        """根据用户关键词从 ERP 搜索审批模板；无授权时返回本地模拟模板。"""
        if user.authorization and user.uid:
            return self._list_remote_templates(user, keyword)
        return [
            ApprovalTemplate(**template) for template in APPROVAL_TEMPLATES.values()
        ]

    def _list_remote_templates(
        self, user: UserContext, keyword: str = ""
    ) -> list[ApprovalTemplate]:
        """从 ERP 审批列表接口获取模板分组。"""
        body = {"keyword": keyword}
        headers = _crm_headers(user)
        payload = self._post_crm_json("approval.list", self._approval_list_url, headers, body)
        if payload.get("code") != 200:
            raise ValueError(f"approval list returned code {payload.get('code')}")
        templates = _templates_from_remote_payload(payload)
        for template in templates:
            self._set_remote_template_cache(
                self._remote_template_by_user_type,
                _remote_template_cache_key(user, template.approval_type),
                template,
            )
        return templates

    def get_template_detail(
        self, approval_type: str, user: UserContext
    ) -> ApprovalTemplate:
        """返回完整模板详情；远程模板会按需补充表单字段。"""
        if approval_type.startswith("remote_"):
            cache_key = _remote_template_cache_key(user, approval_type)
            detail = self._get_remote_template_cache(
                self._remote_template_detail_by_user_type,
                cache_key,
            )
            if detail is not None:
                return detail
            template = self._get_remote_template_cache(
                self._remote_template_by_user_type,
                cache_key,
            )
            if template is None:
                for item in self.list_available_templates(user):
                    if item.approval_type == approval_type:
                        template = item
                        break
            if template is not None:
                detail = self._with_remote_form_fields(template, user)
                self._set_remote_template_cache(
                    self._remote_template_detail_by_user_type,
                    cache_key,
                    detail,
                )
                return detail
        template = APPROVAL_TEMPLATES.get(approval_type)
        if template is None:
            raise ValueError(f"Unknown approval_type: {approval_type}")
        return ApprovalTemplate(**template)

    def _with_remote_form_fields(
        self, template: ApprovalTemplate, user: UserContext
    ) -> ApprovalTemplate:
        """将 ERP 表单字段定义附加到远程审批模板。"""
        if not template.template_id or not user.authorization or (not user.uid):
            return template
        try:
            body = {"field_form": f"approval_type_{template.template_id}"}
            headers = _crm_headers(user)
            payload = self._post_crm_json(
                "field.formFields", self._form_fields_url, headers, body
            )
            if payload.get("code") != 200:
                raise ValueError(f"form fields returned code {payload.get('code')}")
            fields = _fields_from_remote_payload(payload, self, user)
        except Exception as exc:
            logger.warning("Remote form fields failed: %s", exc)
            return template
        if not fields:
            return template
        data = template.model_dump()
        data["fields"] = fields
        return ApprovalTemplate(**data)

    def validate_approval(
        self, approval_type: str, slots: dict[str, Any], user: UserContext
    ) -> ValidationResult:
        """在预览或提交前校验已收集的审批字段。"""
        template = self.get_template_detail(approval_type, user)
        errors: list[str] = []
        field_errors: list[FieldError] = []
        warnings: list[str] = []
        for field in template.fields:
            value = slots.get(field.name, "")
            if field.required and (not value):
                message = f"{field.label}不能为空。"
                errors.append(message)
                field_errors.append(FieldError(field=field.name, message=message))
            if field.type == "enum" and value and (value not in field.options):
                message = f"{field.label}必须是：{', '.join(field.options)}。"
                errors.append(message)
                field_errors.append(FieldError(field=field.name, message=message))
            if field.type == "number" and value and (_safe_number(value) <= 0):
                message = f"{field.label}必须大于 0。"
                errors.append(message)
                field_errors.append(FieldError(field=field.name, message=message))
        if approval_type == "leave":
            start_date = slots.get("start_date", "")
            end_date = slots.get("end_date", "")
            if start_date and end_date and (start_date > end_date):
                message = "开始时间不能晚于结束时间。"
                errors.append(message)
                field_errors.append(FieldError(field="start_date", message=message))
                field_errors.append(FieldError(field="end_date", message=message))
        if (
            approval_type == "expense"
            and _safe_number(slots.get("amount", "0")) >= 5000
        ):
            warnings.append("报销金额较高，将进入部门负责人审批。")
        approval_node = _approval_node(approval_type, slots)
        return ValidationResult(
            valid=not errors,
            errors=errors,
            field_errors=field_errors,
            warnings=warnings,
            approval_node=approval_node,
        )

    def get_approval_nodes(
        self,
        approval_set_id: str,
        form_value: list[dict[str, Any]],
        user: UserContext,
    ) -> list[ApprovalNode]:
        """根据审批模板和表单值获取 CRM 审批流程节点。"""
        if not user.authorization or not user.uid:
            return []
        body = {
            "approval_set_id": int(approval_set_id),
            "form_value": form_value,
        }
        headers = _crm_headers(user)
        payload = self._post_crm_json("approval.getNodes", self._get_nodes_url, headers, body)
        if payload.get("code") != 200:
            raise ValueError(f"approval nodes returned code {payload.get('code')}")
        return _nodes_from_remote_payload(payload)

    def get_related_list(
        self,
        user: UserContext,
        relate_type: str,
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        """从 ERP 拉取关联业务对象列表，例如关联订单。"""
        if not user.authorization or not user.uid:
            return []
        cache_key = _dynamic_options_cache_key(
            user,
            "related_list",
            relate_type,
            keyword,
            page,
            page_size,
        )
        cached = self._get_dynamic_options_cache(cache_key)
        if cached is not None:
            return cached
        body = {
            "relate_type": relate_type,
            "page": page,
            "pageSize": page_size,
            "keyword": keyword,
            "status": 0,
            "created_at": "",
            "hasNoAccess": False,
            "type": "",
        }
        headers = _crm_headers(user)
        payload = self._post_crm_json(
            "company.getRelatedList", self._related_list_url, headers, body
        )
        if payload.get("code") != 200:
            raise ValueError(f"related list returned code {payload.get('code')}")
        data = payload.get("data")
        if isinstance(data, dict):
            items = data.get("data") or data.get("list") or data.get("items") or []
        else:
            items = data or []
        result = [item for item in items if isinstance(item, dict)]
        self._set_dynamic_options_cache(cache_key, result)
        return result

    def get_holiday_rules(self, user: UserContext) -> list[dict[str, Any]]:
        """获取当前用户可用的假期类型选项。"""
        if not user.authorization or not user.uid:
            return []
        cache_key = _dynamic_options_cache_key(user, "holiday_rule")
        cached = self._get_dynamic_options_cache(cache_key)
        if cached is not None:
            return cached
        body: dict[str, Any] = {}
        headers = _crm_headers(user)
        payload = self._post_crm_json(
            "attendance.getHolidayRuleByUser", self._holiday_rule_url, headers, body
        )
        if payload.get("code") != 200:
            raise ValueError(f"holiday rule returned code {payload.get('code')}")
        data = payload.get("data") or []
        result = [item for item in data if isinstance(item, dict)]
        self._set_dynamic_options_cache(cache_key, result)
        return result

    def submit_approval(
        self,
        approval_type: str,
        slots: dict[str, Any],
        user: UserContext,
        idempotency_key: str,
        approval_set_id: str | None = None,
        approval_nodes: list[dict[str, Any]] | None = None,
        selected_assignees: dict[str, list[str]] | None = None,
    ) -> SubmitResult:
        """提交审批申请；远程模板调用 ERP，其他模板使用模拟存储。"""
        if approval_type.startswith("remote_") and approval_set_id and user.authorization and user.uid:
            return self._submit_remote_approval(
                slots=slots,
                user=user,
                approval_set_id=approval_set_id,
                approval_nodes=approval_nodes or [],
                selected_assignees=selected_assignees or {},
            )
        if idempotency_key in self._submitted_by_key:
            return self._submitted_by_key[idempotency_key]
        prefix = {"leave": "LR", "expense": "EX", "purchase": "PR", "seal": "SE"}.get(
            approval_type, "AP"
        )
        result = SubmitResult(
            request_id=f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            status="待审批",
            approval_node=_approval_node(approval_type, slots),
            idempotency_key=idempotency_key,
        )
        self._submitted_by_key[idempotency_key] = result
        return result

    def _submit_remote_approval(
        self,
        slots: dict[str, Any],
        user: UserContext,
        approval_set_id: str,
        approval_nodes: list[dict[str, Any]],
        selected_assignees: dict[str, list[str]],
    ) -> SubmitResult:
        """调用 ERP 创建审批接口。"""
        body = {
            "approval_set_id": int(approval_set_id),
            "node_list": _remote_submit_nodes(approval_nodes, selected_assignees),
            "form_data": _remote_form_data(slots),
        }
        headers = _crm_headers(user)
        payload = self._post_crm_json("approval.add", self._add_approval_url, headers, body)
        if payload.get("code") != 200:
            raise ValueError(f"approval add returned code {payload.get('code')}")
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        request_id = str(data.get("request_id") or data.get("id") or "")
        return SubmitResult(
            request_id=request_id,
            status=str(data.get("status") or "待审批"),
            approval_node="CRM审批流",
            idempotency_key=None,
        )

    def _set_remote_template_cache(
        self,
        cache: dict[tuple[str, str], dict[str, Any]],
        key: tuple[str, str],
        template: ApprovalTemplate,
    ) -> None:
        """写入带过期时间的远程模板缓存。"""
        if self._template_cache_ttl_seconds <= 0:
            return
        cache[key] = {
            "expires_at": self._clock() + self._template_cache_ttl_seconds,
            "template": template,
        }

    def _get_remote_template_cache(
        self,
        cache: dict[tuple[str, str], dict[str, Any]],
        key: tuple[str, str],
    ) -> ApprovalTemplate | None:
        """读取远程模板缓存，过期则删除并返回空。"""
        item = cache.get(key)
        if not item:
            return None
        if item["expires_at"] <= self._clock():
            cache.pop(key, None)
            return None
        return item["template"]

    def _set_dynamic_options_cache(
        self, key: tuple[Any, ...], value: list[dict[str, Any]]
    ) -> None:
        """写入动态下拉缓存。"""
        if self._dynamic_options_cache_ttl_seconds <= 0:
            return
        self._dynamic_options_cache[key] = {
            "expires_at": self._clock() + self._dynamic_options_cache_ttl_seconds,
            "value": deepcopy(value),
        }

    def _get_dynamic_options_cache(
        self, key: tuple[Any, ...]
    ) -> list[dict[str, Any]] | None:
        """读取动态下拉缓存，过期则删除。"""
        item = self._dynamic_options_cache.get(key)
        if not item:
            return None
        if item["expires_at"] <= self._clock():
            self._dynamic_options_cache.pop(key, None)
            return None
        return deepcopy(item["value"])

    def _post_crm_json(
        self,
        event: str,
        url: str,
        headers: dict[str, str],
        body: dict[str, Any],
    ) -> dict[str, Any]:
        """统一调用 CRM POST JSON 接口并记录耗时摘要。"""
        started_at = self._clock()
        status_code: int | None = None
        try:
            _log_crm_request(event, url, headers, body)
            response = self._http_client.post(url, headers=headers, json=body)
            status_code = response.status_code
            response.raise_for_status()
            payload = response.json()
            _log_crm_response(event, payload)
            _log_crm_timing(event, url, started_at, self._clock(), True, status_code)
            return payload
        except Exception as exc:
            _log_crm_timing(
                event,
                url,
                started_at,
                self._clock(),
                False,
                status_code,
                str(exc),
            )
            raise


def _approval_node(approval_type: str, slots: dict[str, str]) -> str:
    """根据模板类型和字段值选择模拟审批节点。"""
    if approval_type == "expense" and _safe_number(slots.get("amount", "0")) >= 5000:
        return "部门负责人审批"
    if approval_type == "purchase" and _safe_number(slots.get("budget", "0")) >= 10000:
        return "采购主管审批"
    if approval_type == "seal":
        return "行政负责人审批"
    return "直属主管审批"


def _remote_template_cache_key(
    user: UserContext,
    approval_type: str,
) -> tuple[str, str]:
    """构建远程模板缓存 key，避免不同用户权限下互相复用。"""
    return (user.uid or user.user_id, approval_type)


def _dynamic_options_cache_key(user: UserContext, source: str, *parts: Any) -> tuple[Any, ...]:
    """构建动态选项缓存 key，避免不同用户权限下互相复用。"""
    return (user.uid or user.user_id, source, *parts)


def _template_cache_ttl_from_env() -> int:
    """读取远程模板缓存 TTL。0 表示禁用缓存。"""
    raw_value = os.getenv("AI_APPROVAL_TEMPLATE_CACHE_TTL_SECONDS", "")
    if not raw_value:
        return DEFAULT_TEMPLATE_CACHE_TTL_SECONDS
    try:
        return max(0, int(raw_value))
    except ValueError:
        return DEFAULT_TEMPLATE_CACHE_TTL_SECONDS


def _dynamic_options_cache_ttl_from_env() -> int:
    """读取动态下拉缓存 TTL。0 表示禁用缓存。"""
    raw_value = os.getenv("AI_APPROVAL_DYNAMIC_OPTIONS_CACHE_TTL_SECONDS", "")
    if not raw_value:
        return DEFAULT_DYNAMIC_OPTIONS_CACHE_TTL_SECONDS
    try:
        return max(0, int(raw_value))
    except ValueError:
        return DEFAULT_DYNAMIC_OPTIONS_CACHE_TTL_SECONDS


def _crm_headers(user: UserContext) -> dict[str, str]:
    """构建 CRM 接口请求头。"""
    return {
        "Accept": "application/json, text/plain, */*",
        "Content-Type": "application/json;charset=UTF-8",
        "Authorization": user.authorization or "",
        "UID": user.uid or "",
    }


def _log_crm_request(
    event: str, url: str, headers: dict[str, str], body: dict[str, Any]
) -> None:
    """记录 CRM 请求，Authorization 会在日志服务中脱敏。"""
    write_debug_log(
        f"crm.{event}.request",
        {
            "url": url,
            "headers": headers,
            "body": body,
        },
    )


def _log_crm_response(event: str, payload: dict[str, Any]) -> None:
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
    write_debug_log(f"crm.{event}.response", summary)


def _log_crm_timing(
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
    write_debug_log(f"crm.{event}.timing", payload)


def _templates_from_remote_payload(payload: dict[str, Any]) -> list[ApprovalTemplate]:
    """将 ERP 审批列表响应分组映射为内部模板。"""
    templates: list[ApprovalTemplate] = []
    for group_index, group in enumerate(payload.get("data") or []):
        category = str(group.get("name") or "未分类")
        approvals = group.get("approvals") or []
        if not isinstance(approvals, list):
            continue
        for item_index, item in enumerate(approvals):
            if not isinstance(item, dict):
                continue
            approval_id = str(item.get("id") or "").strip()
            title = str(item.get("name") or "").strip()
            if not approval_id or not title:
                continue
            raw_type = str(item.get("approval_type") or item.get("type") or "").strip()
            approval_type = f"remote_{approval_id}"
            aliases = _remote_aliases(title)
            if raw_type:
                aliases.append(raw_type)
            intent_keywords = _remote_intent_keywords(title)
            if raw_type:
                intent_keywords.append(raw_type)
            templates.append(
                ApprovalTemplate(
                    template_id=approval_id,
                    approval_type=approval_type,
                    title=title,
                    category=category,
                    group_name=category,
                    aliases=list(dict.fromkeys(aliases)),
                    intent_keywords=list(dict.fromkeys(intent_keywords)),
                    is_common=bool(
                        item.get("is_common")
                        or item.get("is_dynamic_common")
                        or item.get("is_used")
                    ),
                    sort_order=group_index * 1000 + item_index,
                    fields=[
                        {
                            "name": "description",
                            "label": "审批说明",
                            "type": "text",
                            "required": True,
                            "aliases": ["说明", "原因", "内容"],
                            "question": "请补充这条审批需要提交的说明。",
                        }
                    ],
                )
            )
    return templates


def _fields_from_remote_payload(
    payload: dict[str, Any],
    service: CrmApprovalService | None = None,
    user: UserContext | None = None,
) -> list[dict[str, Any]]:
    """将 ERP 表单字段响应映射为内部字段字典。"""
    raw_fields = _flatten_remote_fields(payload.get("data") or [])
    mapped_fields: list[dict[str, Any]] = []
    for item in raw_fields:
        required = int(item.get("is_required") or 0) == 1
        if not required:
            continue
        raw_field_type = str(item.get("field_type") or "")
        field_type = _map_remote_field_type(raw_field_type)
        if not field_type:
            continue
        field_key = str(item.get("field_key") or item.get("field_id") or "").strip()
        field_name = str(item.get("field_name") or field_key).strip()
        if not field_key or not field_name:
            continue
        extend = item.get("extend") if isinstance(item.get("extend"), dict) else {}
        option_values = _remote_option_values_for_field(item, service, user)
        options = [str(option["label"]) for option in option_values]
        parent_group = (
            item.get("_parent_group") if isinstance(item.get("_parent_group"), dict) else {}
        )
        mapped_fields.append(
            {
                "name": field_key,
                "label": field_name,
                "type": field_type,
                "input_type": _remote_input_type(raw_field_type, extend),
                "required": required,
                "options": options,
                "option_values": option_values,
                "group_key": parent_group.get("group_key") or None,
                "group_label": parent_group.get("group_label") or None,
                "group_type": parent_group.get("group_type") or None,
                "aliases": _remote_field_aliases(field_name),
                "extract_patterns": [],
                "question": _remote_field_question(field_name, extend, options),
            }
        )
    return mapped_fields


def _nodes_from_remote_payload(payload: dict[str, Any]) -> list[ApprovalNode]:
    """将 ERP 审批节点响应映射为内部节点模型。"""
    nodes: list[ApprovalNode] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        handle = _remote_node_handle(item.get("handle"))
        handle_type = str(handle.get("type") or "").strip() or None
        candidates = _assignees_from_remote(handle.get("relate_user") or [])
        requires_selection = handle_type == "submitter_choice"
        selected = [] if requires_selection else candidates
        nodes.append(
            ApprovalNode(
                node_id=str(item.get("id") or ""),
                node_name=str(item.get("name") or ""),
                node_type=str(item.get("type") or ""),
                level=int(item.get("level") or 0),
                handle_type=handle_type,
                multiple=int(handle.get("is_single") or 0) != 1,
                requires_selection=requires_selection,
                candidate_assignees=candidates,
                selected_assignees=selected,
                raw_node=deepcopy(item),
            )
        )
    return nodes


def _remote_node_handle(value: Any) -> dict[str, Any]:
    """从 ERP 节点 handle 中取出实际处理配置。"""
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        handles = [item for item in value if isinstance(item, dict)]
        selected = next(
            (
                item
                for item in handles
                if str(item.get("type") or "").strip() == "submitter_choice"
            ),
            None,
        )
        return selected or (handles[0] if handles else {})
    return {}


def _remote_submit_nodes(
    approval_nodes: list[dict[str, Any]],
    selected_assignees: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """构建创建审批接口需要的 node_list。"""
    nodes = [ApprovalNode(**item) for item in approval_nodes]
    submit_nodes: list[dict[str, Any]] = []
    for node in nodes:
        selected_uids = selected_assignees.get(node.node_id, [])
        if selected_uids:
            users = [
                user
                for user in node.candidate_assignees
                if user.uid in set(selected_uids)
            ]
        else:
            users = node.selected_assignees
        submit_node = _base_submit_node(node)
        submit_node["handle_uids"] = [_int_uid(user.uid) for user in users]
        submit_node["handle_uids_info"] = [
            {
                "uid": _int_uid(user.uid),
                "name": user.name,
                "avatar": user.avatar,
            }
            for user in users
        ]
        submit_node.setdefault("cc_uid_types", [])
        submit_node.setdefault("cc_uids_info", [])
        submit_node.setdefault("cc_uids", [])
        submit_node.setdefault("cc_handle_uids", [])
        submit_node.setdefault("assign_users", [])
        submit_nodes.append(submit_node)
    return submit_nodes


def _base_submit_node(node: ApprovalNode) -> dict[str, Any]:
    """基于 CRM 原始节点构建提交节点，避免丢失接口需要的字段。"""
    if node.raw_node:
        return deepcopy(node.raw_node)
    return {
        "id": int(node.node_id),
        "type": node.node_type,
        "name": node.node_name,
        "level": node.level,
    }


def _remote_form_data(slots: dict[str, Any]) -> dict[str, Any]:
    """构建创建审批接口需要的 form_data。"""
    form_data: dict[str, Any] = {}
    for key, value in slots.items():
        if isinstance(value, (dict, list)):
            form_data[key] = value
        else:
            form_data[key] = {"value": value}
    return form_data


def _int_uid(uid: str) -> int:
    """将审批人 UID 转为创建接口使用的整数。"""
    return int(uid)


def _assignees_from_remote(items: list[Any]) -> list[ApprovalAssignee]:
    """将 ERP 用户列表映射为审批人模型。"""
    assignees: list[ApprovalAssignee] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid") or "").strip()
        name = str(item.get("display_name") or item.get("name") or "").strip()
        if not uid or not name:
            continue
        assignees.append(
            ApprovalAssignee(
                uid=uid,
                name=name,
                avatar=str(item.get("avatar") or "").strip() or None,
            )
        )
    return assignees


def _flatten_remote_fields(
    items: list[Any], parent_group: dict[str, str] | None = None
) -> list[dict[str, Any]]:
    """将嵌套 ERP 控件组展开为排序后的字段列表。"""
    fields: list[dict[str, Any]] = []
    for item in sorted(
        (value for value in items if isinstance(value, dict)),
        key=lambda value: int(value.get("sort") or 0),
    ):
        children = item.get("_child") or []
        if isinstance(children, list) and children:
            group = {
                "group_key": str(item.get("field_key") or item.get("field_id") or "").strip(),
                "group_label": str(item.get("field_name") or "").strip(),
                "group_type": _remote_group_type(str(item.get("field_type") or "")),
            }
            fields.extend(_flatten_remote_fields(children, group))
        else:
            field = deepcopy(item)
            if parent_group:
                field["_parent_group"] = parent_group
            fields.append(field)
    return fields


def _remote_group_type(field_type: str) -> str:
    """将 ERP 父控件类型映射为内部复杂字段分组类型。"""
    if field_type in {"detail", "detail_table", "table"}:
        return "detail_table"
    return "complex_group"


def _map_remote_field_type(field_type: str) -> str | None:
    """将 ERP 字段类型映射为内部支持的字段类型。"""
    if field_type in {"date", "datetime", "attendance_date"}:
        return "date"
    if field_type in {"number", "money", "duration"}:
        return "number"
    if field_type in {"select", "radio", "checkbox"}:
        return "enum"
    if field_type == "checkbox_order":
        return "enum"
    if field_type in {"input", "textarea", "address"}:
        return "text"
    return None


def _remote_input_type(field_type: str, extend: dict[str, Any]) -> str:
    """将 ERP 字段类型映射为前端控件类型。"""
    if field_type in {"date", "datetime", "attendance_date"}:
        date_type = str(extend.get("date_type") or "").strip()
        if field_type == "date" and date_type == "date":
            return "date"
        return "datetime"
    if field_type == "textarea":
        return "textarea"
    if field_type == "address":
        return "address"
    if field_type in {"select", "radio", "checkbox", "checkbox_order"}:
        return "single_select"
    return "text"


def _remote_related_type(item: dict[str, Any]) -> str | None:
    """识别需要额外拉取候选列表的 ERP 关联字段。"""
    field_type = str(item.get("field_type") or "")
    if field_type == "checkbox_order":
        return "crmOrder"
    return None


def _remote_option_values_for_field(
    item: dict[str, Any],
    service: CrmApprovalService | None,
    user: UserContext | None,
) -> list[dict[str, Any]]:
    """按静态配置、关联字段、动态接口的优先级解析字段选项。"""
    static_options = _remote_field_option_values(item)
    if static_options:
        return static_options
    if not service or not user:
        return []
    related_type = _remote_related_type(item)
    if related_type:
        return _remote_related_option_values(service, user, related_type)
    field_key = str(item.get("field_key") or item.get("field_id") or "").strip()
    dynamic_option_source = _remote_dynamic_option_source(field_key)
    if dynamic_option_source:
        return _remote_dynamic_option_values(service, user, dynamic_option_source)
    return []


def _remote_related_options(
    service: CrmApprovalService,
    user: UserContext,
    relate_type: str,
) -> list[str]:
    """将关联业务对象列表转换为可供聊天选择的文本选项。"""
    try:
        items = service.get_related_list(user, relate_type)
    except Exception as exc:
        logger.warning("Remote related list failed: %s", exc)
        return []
    options: list[str] = []
    for item in items:
        text = _related_item_label(item)
        if text:
            options.append(text)
    return list(dict.fromkeys(options))


def _remote_related_option_values(
    service: CrmApprovalService,
    user: UserContext,
    relate_type: str,
) -> list[dict[str, Any]]:
    """将关联业务对象列表转换为结构化选项。"""
    return [
        {"label": label, "value": label}
        for label in _remote_related_options(service, user, relate_type)
    ]


def _remote_dynamic_option_source(field_key: str) -> str | None:
    """维护特殊字段到选项接口的映射。"""
    return DYNAMIC_OPTION_FIELD_SOURCES.get(field_key)


def _remote_dynamic_option_values(
    service: CrmApprovalService,
    user: UserContext,
    source: str,
) -> list[dict[str, Any]]:
    """按特殊字段来源拉取结构化选项。"""
    if source == "holiday_rule":
        try:
            return _holiday_rule_option_values(service.get_holiday_rules(user))
        except Exception as exc:
            logger.warning("Remote holiday rules failed: %s", exc)
            return []
    return []


def _holiday_rule_option_values(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """将假期规则转换为前端单选项。"""
    options: list[dict[str, Any]] = []
    for item in items:
        rule_id = item.get("id")
        name = str(item.get("name") or "").strip()
        if rule_id is None or not name:
            continue
        label = _holiday_rule_label(item, name)
        options.append({"label": label, "value": rule_id})
    return options


def _holiday_rule_label(item: dict[str, Any], name: str) -> str:
    """保持与 ERP 表单假期类型下拉一致的 label。"""
    unit = "小时" if item.get("time_unit") == "hour" else "天"
    if int(item.get("balance_rule") or 0) == 1:
        balance = item.get("balance") or "0"
        return f"{name}（余{balance}{unit}）"
    json_rule = item.get("json_rule") if isinstance(item.get("json_rule"), dict) else {}
    if int(json_rule.get("is_continuous_holidays") or 0) == 1:
        days = json_rule.get("continuous_holidays_day") or "0"
        return f"{name}（{days}{unit}）"
    return name


def _related_item_label(item: dict[str, Any]) -> str:
    """从常见 ERP 关联对象字段中挑选用户可读名称。"""
    for key in ("order_num", "name", "title", "num", "no", "id"):
        value = item.get(key)
        if isinstance(value, dict):
            value = value.get("text") or value.get("value") or value.get("name")
        text = str(value or "").strip()
        if text:
            return text
    return ""


def _remote_field_options(item: dict[str, Any]) -> list[str]:
    """从 ERP 字段定义中抽取枚举选项。"""
    return [str(option["label"]) for option in _remote_field_option_values(item)]


def _remote_field_option_values(item: dict[str, Any]) -> list[dict[str, Any]]:
    """从 ERP 字段定义中抽取结构化枚举选项。"""
    extend = item.get("extend") if isinstance(item.get("extend"), dict) else {}
    options = extend.get("options") or extend.get("option") or item.get("options") or []
    if not isinstance(options, list):
        return []
    normalized: list[dict[str, Any]] = []
    for option in options:
        if isinstance(option, dict):
            label = option.get("label") or option.get("name") or option.get("value")
            value = option.get("value", label)
        else:
            label = option
            value = option
        text = str(label or "").strip()
        if text:
            normalized.append({"label": text, "value": value})
    return normalized


def _remote_field_aliases(field_name: str) -> list[str]:
    """构建便于文本抽取匹配字段的简单别名。"""
    aliases = {field_name}
    for word in ("时间", "地点", "事由", "说明", "原因", "内容", "地址"):
        if word in field_name:
            aliases.add(word)
    return [alias for alias in aliases if alias]


def _remote_field_question(
    field_name: str, extend: dict[str, Any], options: list[str] | None = None
) -> str:
    """选择 ERP 字段对应的用户追问文案。"""
    option_text = "、".join(options or [])
    for key in (
        "placeholder",
        "area_accuracy_placeholder",
        "detail_address_placeholder",
    ):
        value = str(extend.get(key) or "").strip()
        if value:
            if option_text:
                return f"{value}，可选：{option_text}。"
            return value
    if option_text:
        return f"请选择{field_name}，可选：{option_text}。"
    return f"请补充{field_name}。"


def _remote_aliases(title: str) -> list[str]:
    """根据 ERP 常见命名前缀构建模板别名。"""
    aliases = {title}
    for prefix in ("zh-", "测试", "审批编辑-"):
        if title.startswith(prefix):
            aliases.add(title.removeprefix(prefix))
    return [alias for alias in aliases if alias]


def _remote_intent_keywords(title: str) -> list[str]:
    """根据 ERP 模板标题构建意图关键词。"""
    keywords = set(_remote_aliases(title))
    for word in (
        "请假",
        "报销",
        "采购",
        "用章",
        "外出",
        "出差",
        "加班",
        "入库",
        "出库",
    ):
        if word in title:
            keywords.add(word)
    return [keyword for keyword in keywords if keyword]


def _safe_number(value: str) -> float:
    """将包含数字的文本转换为浮点数，供模拟规则使用。"""
    digits = "".join((ch for ch in str(value) if ch.isdigit() or ch == "."))
    if not digits:
        return 0.0
    return float(digits)


crm_approval_service = CrmApprovalService()

from __future__ import annotations
from copy import deepcopy
from datetime import datetime, timedelta
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
from app.services.approval_payload_builder import (
    remote_form_data,
    remote_submit_nodes,
)
from app.services.crm_api_client import CrmApiClient
from app.services.crm_mapper import (
    fields_from_remote_payload,
    nodes_from_remote_payload,
    templates_from_remote_payload,
)
from app.services.debug_log_service import write_debug_log

logger = logging.getLogger("ai_approval_assistant.crm")

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
        calculate_holiday_duration_url: str | None = None,
        user_list_url: str | None = None,
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
        self._api_client = CrmApiClient(
            http_client=http_client,
            approval_list_url=approval_list_url,
            form_fields_url=form_fields_url,
            get_nodes_url=get_nodes_url,
            add_approval_url=add_approval_url,
            related_list_url=related_list_url,
            holiday_rule_url=holiday_rule_url,
            calculate_holiday_duration_url=calculate_holiday_duration_url,
            user_list_url=user_list_url,
            clock=self._clock,
            log_writer=write_debug_log,
        )

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
            templates = self._list_remote_templates(user, keyword)
            if templates:
                return templates

            # ERP 的模板搜索通常只支持短标题/关键词。用户从聊天输入的往往是
            # 完整自然语言句子，整句搜索为空时用审批类型关键词重试一次。
            for fallback_keyword in _approval_search_keywords(keyword):
                if fallback_keyword == keyword:
                    continue
                templates = self._list_remote_templates(user, fallback_keyword)
                if templates:
                    return templates
            return templates
        return [
            ApprovalTemplate(**template) for template in APPROVAL_TEMPLATES.values()
        ]

    def _list_remote_templates(
        self, user: UserContext, keyword: str = ""
    ) -> list[ApprovalTemplate]:
        """从 ERP 审批列表接口获取模板分组。"""
        payload = self._api_client.list_approvals(user, keyword)
        if payload.get("code") != 200:
            raise ValueError(f"approval list returned code {payload.get('code')}")
        templates = templates_from_remote_payload(payload)
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
            payload = self._api_client.get_form_fields(user, template.template_id)
            if payload.get("code") != 200:
                raise ValueError(f"form fields returned code {payload.get('code')}")
            fields = fields_from_remote_payload(payload, self, user)
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
        payload = self._api_client.get_approval_nodes(user, approval_set_id, form_value)
        if payload.get("code") != 200:
            raise ValueError(f"approval nodes returned code {payload.get('code')}")
        nodes = nodes_from_remote_payload(payload)
        if any(_needs_company_user_candidates(node) for node in nodes):
            candidates = self._get_company_user_candidates(user)
            for node in nodes:
                if _needs_company_user_candidates(node):
                    node.candidate_assignees = candidates
        return nodes

    def _get_company_user_candidates(
        self, user: UserContext
    ) -> list[ApprovalAssignee]:
        """获取 ERP 页面在全公司自选场景使用的人员列表。"""
        payload = self._api_client.get_user_list(user)
        if payload.get("code") != 200:
            raise ValueError(f"user list returned code {payload.get('code')}")
        return _approval_assignees_from_users(payload.get("data") or [])

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
        payload = self._api_client.get_related_list(
            user,
            relate_type,
            keyword=keyword,
            page=page,
            page_size=page_size,
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
        payload = self._api_client.get_holiday_rules(user)
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
        form_data = self._remote_submission_form_data(slots, user)
        payload = self._api_client.add_approval(
            user,
            approval_set_id,
            node_list=remote_submit_nodes(approval_nodes, selected_assignees),
            form_data=form_data,
        )
        if payload.get("code") != 200:
            raise ValueError(
                f"approval add returned code {payload.get('code')}: "
                f"{payload.get('message') or 'unknown error'}"
            )
        data = payload.get("data") if isinstance(payload.get("data"), dict) else {}
        request_id = str(data.get("request_id") or data.get("id") or "")
        return SubmitResult(
            request_id=request_id,
            status=str(data.get("status") or "待审批"),
            approval_node="CRM审批流",
            idempotency_key=None,
        )

    def _remote_submission_form_data(
        self,
        slots: dict[str, Any],
        user: UserContext,
    ) -> dict[str, Any]:
        """补齐 ERP 特殊控件依赖的派生提交字段。"""
        form_data = remote_form_data(slots)
        holiday_rule = _structured_value(form_data.get("rest_holiday_rule_id"))
        start_date = _structured_value(form_data.get("rest_start_time"))
        end_date = _structured_value(form_data.get("rest_end_time"))
        if holiday_rule is None or not start_date or not end_date:
            return form_data

        rules = self.get_holiday_rules(user)
        selected_rule = next(
            (item for item in rules if str(item.get("id")) == str(holiday_rule)),
            None,
        )
        if not selected_rule:
            raise ValueError("selected holiday rule not found")

        start_date, end_date = _normalize_leave_time_fields(
            form_data,
            selected_rule,
            str(start_date),
            str(end_date),
        )

        duration_payload = self._api_client.calculate_holiday_duration(
            user,
            int(holiday_rule),
            start_date,
            end_date,
        )
        if duration_payload.get("code") != 200:
            raise ValueError(
                "calculate holiday duration returned code "
                f"{duration_payload.get('code')}: {duration_payload.get('message') or ''}"
            )
        duration_data = (
            duration_payload.get("data")
            if isinstance(duration_payload.get("data"), dict)
            else {}
        )
        rest_rule_json = deepcopy(selected_rule)
        rest_rule_json["holiday_day_list"] = duration_data.get("holiday_day_list") or []
        rest_rule_json["web_show_day_list"] = duration_data.get("web_show_day_list") or []
        form_data["rest_rule_json"] = rest_rule_json
        if duration_data.get("all_duration") is not None:
            duration_value = duration_data["all_duration"]
            existing_duration = form_data.get("rest_duration")
            if isinstance(existing_duration, dict):
                existing_duration["value"] = duration_value
                existing_duration["label"] = str(duration_value)
            else:
                form_data["rest_duration"] = {"value": duration_value}
        form_data.setdefault("rest_prove", [])
        return form_data

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

def _approval_node(approval_type: str, slots: dict[str, str]) -> str:
    """根据模板类型和字段值选择模拟审批节点。"""
    if approval_type == "expense" and _safe_number(slots.get("amount", "0")) >= 5000:
        return "部门负责人审批"
    if approval_type == "purchase" and _safe_number(slots.get("budget", "0")) >= 10000:
        return "采购主管审批"
    if approval_type == "seal":
        return "行政负责人审批"
    return "直属主管审批"


def _approval_search_keywords(keyword: str) -> list[str]:
    """从自然语言审批请求中提取适合 ERP 模板搜索的短关键词。"""
    markers = (
        "请假",
        "休假",
        "年假",
        "事假",
        "病假",
        "调休",
        "报销",
        "差旅费",
        "采购",
        "用章",
        "盖章",
        "外出",
        "出差",
        "加班",
        "入库",
        "出库",
    )
    return list(dict.fromkeys(marker for marker in markers if marker in keyword))


def _needs_company_user_candidates(node: ApprovalNode) -> bool:
    """判断自选节点是否需要从公司人员接口补齐候选人。"""
    if not node.requires_selection or node.candidate_assignees:
        return False
    handle = node.raw_node.get("handle")
    if isinstance(handle, list):
        handle = next(
            (
                item
                for item in handle
                if isinstance(item, dict)
                and str(item.get("type") or "").strip() == "submitter_choice"
            ),
            {},
        )
    if not isinstance(handle, dict):
        return False
    return int(handle.get("is_all_company") or 0) != 2


def _approval_assignees_from_users(items: Any) -> list[ApprovalAssignee]:
    """将公司人员接口结果转换为审批候选人并按 UID 去重。"""
    if isinstance(items, dict):
        items = items.get("data") or items.get("list") or items.get("items") or []
    candidates: dict[str, ApprovalAssignee] = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid") or item.get("id") or "").strip()
        name = str(item.get("display_name") or item.get("name") or "").strip()
        if not uid or not name:
            continue
        candidates[uid] = ApprovalAssignee(
            uid=uid,
            name=name,
            avatar=str(item.get("avatar") or "").strip() or None,
        )
    return list(candidates.values())


def _structured_value(value: Any) -> Any:
    """读取 ERP 表单结构中的实际值。"""
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _normalize_leave_time_fields(
    form_data: dict[str, Any],
    holiday_rule: dict[str, Any],
    start_date: str,
    end_date: str,
) -> tuple[str, str]:
    """按 ERP 正式请假控件格式整理日期字段。"""
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


def _safe_number(value: str) -> float:
    """将包含数字的文本转换为浮点数，供模拟规则使用。"""
    digits = "".join((ch for ch in str(value) if ch.isdigit() or ch == "."))
    if not digits:
        return 0.0
    return float(digits)


crm_approval_service = CrmApprovalService()

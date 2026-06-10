from __future__ import annotations
from copy import deepcopy
from datetime import datetime
import logging
import os
from typing import Any
import httpx
from ai_approval_assistant.app.mock_data.approval_templates import (
    APPROVAL_TEMPLATES,
    USERS,
)
from ai_approval_assistant.app.schemas.approval import (
    ApprovalAssignee,
    ApprovalNode,
    ApprovalTemplate,
    FieldError,
    SubmitResult,
    UserContext,
    ValidationResult,
)

logger = logging.getLogger("ai_approval_assistant.crm")
DEFAULT_APPROVAL_LIST_URL = "https://dev2.lanerp.com/api/approval/list"
DEFAULT_FORM_FIELDS_URL = "https://dev2.lanerp.com/api/field/formFields"
DEFAULT_GET_NODES_URL = "https://dev2.lanerp.com/api/approval/getNodes"
DEFAULT_ADD_APPROVAL_URL = "https://dev2.lanerp.com/api/approval/add"


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
    ) -> None:
        """初始化 CRM 适配器地址、HTTP 客户端和模拟提交缓存。"""
        self._submitted_by_key: dict[str, SubmitResult] = {}
        self._http_client = http_client or httpx.Client(timeout=10)
        self._approval_list_url = approval_list_url or os.getenv(
            "AI_APPROVAL_LIST_URL", DEFAULT_APPROVAL_LIST_URL
        )
        self._form_fields_url = form_fields_url or os.getenv(
            "AI_APPROVAL_FORM_FIELDS_URL", DEFAULT_FORM_FIELDS_URL
        )
        self._get_nodes_url = get_nodes_url or os.getenv(
            "AI_APPROVAL_GET_NODES_URL", DEFAULT_GET_NODES_URL
        )
        self._add_approval_url = add_approval_url or os.getenv(
            "AI_APPROVAL_ADD_URL", DEFAULT_ADD_APPROVAL_URL
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
        if user.authorization and user.uid:
            try:
                templates = self._list_remote_templates(user)
                if templates:
                    return templates
            except Exception as exc:
                logger.warning("Remote approval list failed: %s", exc)
        return [
            ApprovalTemplate(**template) for template in APPROVAL_TEMPLATES.values()
        ]

    def _list_remote_templates(self, user: UserContext) -> list[ApprovalTemplate]:
        """从 ERP 审批列表接口获取模板分组。"""
        response = self._http_client.post(
            self._approval_list_url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": user.authorization or "",
                "UID": user.uid or "",
            },
            json={"keyword": ""},
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise ValueError(f"approval list returned code {payload.get('code')}")
        return _templates_from_remote_payload(payload)

    def get_template_detail(
        self, approval_type: str, user: UserContext
    ) -> ApprovalTemplate:
        """返回完整模板详情；远程模板会按需补充表单字段。"""
        if approval_type.startswith("remote_"):
            for template in self.list_available_templates(user):
                if template.approval_type == approval_type:
                    return self._with_remote_form_fields(template, user)
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
            response = self._http_client.post(
                self._form_fields_url,
                headers={
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json;charset=UTF-8",
                    "Authorization": user.authorization or "",
                    "UID": user.uid or "",
                },
                json={"field_form": f"approval_type_{template.template_id}"},
            )
            response.raise_for_status()
            payload = response.json()
            if payload.get("code") != 200:
                raise ValueError(f"form fields returned code {payload.get('code')}")
            fields = _fields_from_remote_payload(payload)
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
        response = self._http_client.post(
            self._get_nodes_url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": user.authorization or "",
                "UID": user.uid or "",
            },
            json={
                "approval_set_id": int(approval_set_id),
                "form_value": form_value,
            },
        )
        response.raise_for_status()
        payload = response.json()
        if payload.get("code") != 200:
            raise ValueError(f"approval nodes returned code {payload.get('code')}")
        return _nodes_from_remote_payload(payload)

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
        response = self._http_client.post(
            self._add_approval_url,
            headers={
                "Accept": "application/json, text/plain, */*",
                "Content-Type": "application/json;charset=UTF-8",
                "Authorization": user.authorization or "",
                "UID": user.uid or "",
            },
            json=body,
        )
        response.raise_for_status()
        payload = response.json()
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


def _approval_node(approval_type: str, slots: dict[str, str]) -> str:
    """根据模板类型和字段值选择模拟审批节点。"""
    if approval_type == "expense" and _safe_number(slots.get("amount", "0")) >= 5000:
        return "部门负责人审批"
    if approval_type == "purchase" and _safe_number(slots.get("budget", "0")) >= 10000:
        return "采购主管审批"
    if approval_type == "seal":
        return "行政负责人审批"
    return "直属主管审批"


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


def _fields_from_remote_payload(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """将 ERP 表单字段响应映射为内部字段字典。"""
    raw_fields = _flatten_remote_fields(payload.get("data") or [])
    mapped_fields: list[dict[str, Any]] = []
    for item in raw_fields:
        field_type = _map_remote_field_type(str(item.get("field_type") or ""))
        if not field_type:
            continue
        field_key = str(item.get("field_key") or item.get("field_id") or "").strip()
        field_name = str(item.get("field_name") or field_key).strip()
        if not field_key or not field_name:
            continue
        extend = item.get("extend") if isinstance(item.get("extend"), dict) else {}
        mapped_fields.append(
            {
                "name": field_key,
                "label": field_name,
                "type": field_type,
                "required": int(item.get("is_required") or 0) == 1,
                "options": _remote_field_options(item),
                "aliases": _remote_field_aliases(field_name),
                "extract_patterns": [],
                "question": _remote_field_question(field_name, extend),
            }
        )
    return mapped_fields


def _nodes_from_remote_payload(payload: dict[str, Any]) -> list[ApprovalNode]:
    """将 ERP 审批节点响应映射为内部节点模型。"""
    nodes: list[ApprovalNode] = []
    for item in payload.get("data") or []:
        if not isinstance(item, dict):
            continue
        handle = item.get("handle") if isinstance(item.get("handle"), dict) else {}
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


def _flatten_remote_fields(items: list[Any]) -> list[dict[str, Any]]:
    """将嵌套 ERP 控件组展开为排序后的字段列表。"""
    fields: list[dict[str, Any]] = []
    for item in sorted(
        (value for value in items if isinstance(value, dict)),
        key=lambda value: int(value.get("sort") or 0),
    ):
        children = item.get("_child") or []
        if isinstance(children, list) and children:
            fields.extend(_flatten_remote_fields(children))
        else:
            fields.append(item)
    return fields


def _map_remote_field_type(field_type: str) -> str | None:
    """将 ERP 字段类型映射为内部支持的字段类型。"""
    if field_type in {"date", "datetime"}:
        return "date"
    if field_type in {"number", "money"}:
        return "number"
    if field_type in {"select", "radio", "checkbox"}:
        return "enum"
    if field_type in {"input", "textarea", "address"}:
        return "text"
    return None


def _remote_field_options(item: dict[str, Any]) -> list[str]:
    """从 ERP 字段定义中抽取枚举选项。"""
    extend = item.get("extend") if isinstance(item.get("extend"), dict) else {}
    options = extend.get("options") or extend.get("option") or item.get("options") or []
    if not isinstance(options, list):
        return []
    normalized: list[str] = []
    for option in options:
        if isinstance(option, dict):
            value = option.get("label") or option.get("name") or option.get("value")
        else:
            value = option
        text = str(value or "").strip()
        if text:
            normalized.append(text)
    return normalized


def _remote_field_aliases(field_name: str) -> list[str]:
    """构建便于文本抽取匹配字段的简单别名。"""
    aliases = {field_name}
    for word in ("时间", "地点", "事由", "说明", "原因", "内容", "地址"):
        if word in field_name:
            aliases.add(word)
    return [alias for alias in aliases if alias]


def _remote_field_question(field_name: str, extend: dict[str, Any]) -> str:
    """选择 ERP 字段对应的用户追问文案。"""
    for key in (
        "placeholder",
        "area_accuracy_placeholder",
        "detail_address_placeholder",
    ):
        value = str(extend.get(key) or "").strip()
        if value:
            return value
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

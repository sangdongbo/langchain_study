from __future__ import annotations

from copy import deepcopy
import logging
from typing import Any, Protocol

from app.schemas.approval import (
    ApprovalAssignee,
    ApprovalNode,
    ApprovalTemplate,
    UserContext,
)

logger = logging.getLogger("ai_approval_assistant.crm")

DYNAMIC_OPTION_FIELD_SOURCES = {
    "rest_holiday_rule_id": "holiday_rule",
}


class DynamicOptionProvider(Protocol):
    """远程字段映射时使用的动态选项提供者。"""

    def get_related_list(
        self,
        user: UserContext,
        relate_type: str,
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict[str, Any]]:
        ...

    def get_holiday_rules(self, user: UserContext) -> list[dict[str, Any]]:
        ...


def templates_from_remote_payload(payload: dict[str, Any]) -> list[ApprovalTemplate]:
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


def fields_from_remote_payload(
    payload: dict[str, Any],
    option_provider: DynamicOptionProvider | None = None,
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
        option_values = _remote_option_values_for_field(item, option_provider, user)
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


def nodes_from_remote_payload(payload: dict[str, Any]) -> list[ApprovalNode]:
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


def _remote_option_values_for_field(
    item: dict[str, Any],
    option_provider: DynamicOptionProvider | None,
    user: UserContext | None,
) -> list[dict[str, Any]]:
    """按静态配置、关联字段、动态接口的优先级解析字段选项。"""
    static_options = _remote_field_option_values(item)
    if static_options:
        return static_options
    if not option_provider or not user:
        return []
    related_type = _remote_related_type(item)
    if related_type:
        return _remote_related_option_values(option_provider, user, related_type)
    field_key = str(item.get("field_key") or item.get("field_id") or "").strip()
    dynamic_option_source = _remote_dynamic_option_source(field_key)
    if dynamic_option_source:
        return _remote_dynamic_option_values(option_provider, user, dynamic_option_source)
    return []


def _remote_related_type(item: dict[str, Any]) -> str | None:
    """识别需要额外拉取候选列表的 ERP 关联字段。"""
    field_type = str(item.get("field_type") or "")
    if field_type == "checkbox_order":
        return "crmOrder"
    return None


def _remote_related_option_values(
    option_provider: DynamicOptionProvider,
    user: UserContext,
    relate_type: str,
) -> list[dict[str, Any]]:
    """将关联业务对象列表转换为结构化选项。"""
    return [
        {"label": label, "value": label}
        for label in _remote_related_options(option_provider, user, relate_type)
    ]


def _remote_related_options(
    option_provider: DynamicOptionProvider,
    user: UserContext,
    relate_type: str,
) -> list[str]:
    """将关联业务对象列表转换为可供聊天选择的文本选项。"""
    try:
        items = option_provider.get_related_list(user, relate_type)
    except Exception as exc:
        logger.warning("Remote related list failed: %s", exc)
        return []
    options: list[str] = []
    for item in items:
        text = _related_item_label(item)
        if text:
            options.append(text)
    return list(dict.fromkeys(options))


def _remote_dynamic_option_source(field_key: str) -> str | None:
    """维护特殊字段到选项接口的映射。"""
    return DYNAMIC_OPTION_FIELD_SOURCES.get(field_key)


def _remote_dynamic_option_values(
    option_provider: DynamicOptionProvider,
    user: UserContext,
    source: str,
) -> list[dict[str, Any]]:
    """按特殊字段来源拉取结构化选项。"""
    if source == "holiday_rule":
        try:
            return _holiday_rule_option_values(option_provider.get_holiday_rules(user))
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

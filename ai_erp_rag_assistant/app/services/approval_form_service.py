from __future__ import annotations

from copy import deepcopy
from typing import Any


_CONTAINER_KEYS = ("fields", "list", "data", "items", "children", "_child")
_LAYOUT_GROUP_TYPES = {"control", "group", "section", "fieldset"}
_DETAIL_TYPES = {"detail", "detail_table", "table"}
_USER_TYPES = {"user", "employee", "member", "person", "checkbox_user"}
_DEPARTMENT_TYPES = {"department", "dept", "checkbox_department"}
_ATTACHMENT_TYPES = {"attachment", "attachments", "file", "files", "upload", "image"}


def normalize_erp_fields(data: Any) -> list[dict[str, Any]]:
    """Convert ERP-specific form definitions to one stable frontend contract."""
    items = _field_items(data)
    return _normalize_items(items)


def project_chat_fields(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Keep the compact field shape expected by the conversational workflow."""
    result: list[dict[str, Any]] = []
    for field in fields:
        if not isinstance(field, dict) or not field.get("required"):
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


def build_form_schema(
    template: dict[str, Any],
    values: dict[str, Any] | None = None,
    *,
    missing_field_keys: list[str] | None = None,
    invalid_fields: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Build the complete dynamic-form payload returned to a frontend."""
    raw_fields = template.get("all_fields") or template.get("fields") or []
    fields = (
        deepcopy(raw_fields)
        if all(isinstance(field, dict) and field.get("component") for field in raw_fields)
        else normalize_erp_fields(raw_fields)
    )
    return {
        "schema_version": "1.0",
        "template": {
            "template_id": str(template.get("template_id") or template.get("template_code") or ""),
            "template_code": str(template.get("template_code") or template.get("template_id") or ""),
            "title": str(template.get("title") or ""),
            "company_id": str(template.get("company_id") or ""),
        },
        "fields": fields,
        "values": deepcopy(values or {}),
        "missing_field_keys": list(missing_field_keys or []),
        "invalid_fields": deepcopy(invalid_fields or []),
    }


def find_field(fields: list[dict[str, Any]], field_key: str) -> dict[str, Any] | None:
    for field in fields:
        if str(field.get("name") or "") == str(field_key):
            return field
        child = find_field(field.get("children") or [], field_key)
        if child:
            return child
    return None


def normalize_approval_nodes(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Expose approval routing without forcing the frontend to parse ERP handle data."""
    result: list[dict[str, Any]] = []
    for item in nodes:
        if not isinstance(item, dict):
            continue
        handle = _node_handle(item.get("handle"))
        candidates = _assignees(handle)
        handle_type = str(handle.get("type") or "").strip()
        requires_selection = handle_type == "submitter_choice"
        result.append(
            {
                "node_id": str(item.get("id") or ""),
                "name": str(item.get("name") or ""),
                "node_type": str(item.get("type") or ""),
                "level": int(item.get("level") or 0),
                "handle_type": handle_type,
                "requires_selection": requires_selection,
                "multiple": int(handle.get("is_single") or 0) != 1,
                "candidates": candidates,
                "selected": [] if requires_selection else candidates,
            }
        )
    return result


def build_submit_nodes(
    nodes: list[dict[str, Any]],
    selected_assignees: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """Keep ERP node metadata and apply submitter-selected assignees."""
    selected_assignees = selected_assignees or {}
    submit_nodes: list[dict[str, Any]] = []
    for raw_node, frontend_node in zip(nodes, normalize_approval_nodes(nodes), strict=False):
        node = deepcopy(raw_node)
        node_id = frontend_node["node_id"]
        candidates = frontend_node["candidates"]
        requested = {str(uid) for uid in selected_assignees.get(node_id, [])}
        selected = [item for item in candidates if not requested or str(item["uid"]) in requested]
        if frontend_node["requires_selection"] and not requested:
            selected = []
        node["handle_uids"] = [_numeric_uid(item["uid"]) for item in selected]
        node["handle_uids_info"] = [
            {
                "uid": _numeric_uid(item["uid"]),
                "name": item["name"],
                "avatar": item.get("avatar"),
            }
            for item in selected
        ]
        node.setdefault("cc_uid_types", [])
        node.setdefault("cc_uids_info", [])
        node.setdefault("cc_uids", [])
        node.setdefault("cc_handle_uids", [])
        node.setdefault("assign_users", [])
        submit_nodes.append(node)
    return submit_nodes


def missing_assignee_nodes(
    approval_flow: list[dict[str, Any]],
    selected_assignees: dict[str, list[str]] | None,
) -> list[str]:
    selected_assignees = selected_assignees or {}
    return [
        str(node.get("node_id") or "")
        for node in approval_flow
        if node.get("requires_selection")
        and not selected_assignees.get(str(node.get("node_id") or ""))
    ]


def _field_items(data: Any) -> list[dict[str, Any]]:
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    if data.get("field_key") or data.get("field_id"):
        return [data]
    for key in _CONTAINER_KEYS:
        items = _field_items(data.get(key))
        if items:
            return items
    return []


def _normalize_items(
    items: list[dict[str, Any]],
    parent_group: dict[str, str] | None = None,
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    for item in sorted(items, key=lambda value: int(value.get("sort") or 0)):
        raw_type = str(item.get("field_type") or item.get("type") or item.get("input_type") or "input").lower()
        children = _field_items(item.get("_child") or item.get("children") or item.get("fields"))
        if children and raw_type in _LAYOUT_GROUP_TYPES:
            group = {
                "key": _field_key(item),
                "label": _field_label(item),
                "type": "field-group",
            }
            result.extend(_normalize_items(children, group))
            continue
        result.append(_normalize_field(item, raw_type, children, parent_group))
    return [field for field in result if field.get("name")]


def _normalize_field(
    item: dict[str, Any],
    raw_type: str,
    children: list[dict[str, Any]],
    parent_group: dict[str, str] | None,
) -> dict[str, Any]:
    name = _field_key(item)
    label = _field_label(item) or name
    extend = item.get("extend") if isinstance(item.get("extend"), dict) else {}
    required = item.get("required", item.get("is_required", item.get("isRequired", False))) in (
        True,
        1,
        "1",
        "true",
        "True",
    )
    component, value_type, legacy_type = _component_types(raw_type, extend)
    option_values = _option_values(item, extend)
    multiple = raw_type in {"checkbox", "checkbox_order", "checkbox_approval"} or bool(extend.get("multiple"))
    child_fields = _normalize_items(children) if children else []
    if raw_type in _DETAIL_TYPES and child_fields:
        child_fields = [dict(field, required=False) for field in child_fields]
    if raw_type in _DETAIL_TYPES:
        component, value_type, legacy_type = "detail-table", "array", "array"
    validation = {
        key: value
        for key, value in {
            "min": extend.get("min"),
            "max": extend.get("max"),
            "min_length": extend.get("min_length"),
            "max_length": extend.get("max_length"),
            "pattern": extend.get("pattern") or extend.get("regex"),
        }.items()
        if value not in (None, "")
    }
    return {
        "name": name,
        "label": label,
        "required": required,
        "type": legacy_type,
        "component": component,
        "value_type": value_type,
        "erp_field_type": raw_type,
        "input_type": str(item.get("input_type") or ""),
        "options": [str(option["label"]) for option in option_values],
        "option_values": option_values,
        "option_source": _option_source(name, raw_type, item, extend, option_values),
        "validation": validation,
        "group": deepcopy(parent_group),
        "group_key": (parent_group or {}).get("key"),
        "group_label": (parent_group or {}).get("label"),
        "group_type": (parent_group or {}).get("type"),
        "ui": {
            "placeholder": str(
                extend.get("placeholder")
                or extend.get("area_accuracy_placeholder")
                or extend.get("detail_address_placeholder")
                or ""
            ),
            "multiple": multiple,
            "readonly": bool(item.get("readonly") or extend.get("readonly")),
            "hidden": bool(item.get("hidden") or extend.get("hidden")),
            "col_span": extend.get("col_span"),
        },
        "children": child_fields,
        "erp": {
            "field_key": name,
            "field_id": str(item.get("field_id") or ""),
            "field_type": raw_type,
            "sort": int(item.get("sort") or 0),
        },
    }


def _component_types(raw_type: str, extend: dict[str, Any]) -> tuple[str, str, str]:
    if raw_type == "textarea":
        return "textarea", "string", "text"
    if raw_type in {"number", "duration"}:
        return "number", "number", "number"
    if raw_type == "money":
        return "money", "number", "number"
    if raw_type == "date" and str(extend.get("date_type") or "") == "date":
        return "date", "date", "date"
    if raw_type in {"date", "datetime", "attendance_date"}:
        return "datetime", "datetime", "datetime"
    if raw_type == "radio":
        return "radio", "string", "enum"
    if raw_type == "select":
        return "select", "string", "enum"
    if raw_type == "checkbox":
        return "checkbox-group", "array", "enum"
    if raw_type == "checkbox_order":
        return "related-select", "array", "array"
    if raw_type == "checkbox_approval":
        return "approval-select", "array", "array"
    if raw_type in _USER_TYPES:
        return "entity-select", "array", "array"
    if raw_type in _DEPARTMENT_TYPES:
        return "entity-select", "array", "array"
    if raw_type in _ATTACHMENT_TYPES:
        return "attachment", "array", "array"
    if raw_type == "address":
        return "address", "object", "text"
    return "text", "string", "text"


def _option_source(
    name: str,
    raw_type: str,
    item: dict[str, Any],
    extend: dict[str, Any],
    option_values: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if option_values:
        return {"type": "static", "lazy": False, "searchable": False}
    if name == "rest_holiday_rule_id":
        return {"type": "holiday_rule", "lazy": False, "searchable": False}
    if raw_type == "checkbox_order":
        return {
            "type": "related_list",
            "relate_type": str(item.get("relate_type") or extend.get("relate_type") or "crmOrder"),
            "lazy": True,
            "searchable": True,
        }
    if raw_type == "checkbox_approval":
        return {"type": "related_list", "relate_type": "approval", "lazy": True, "searchable": True}
    if raw_type in _USER_TYPES:
        return {"type": "user_list", "lazy": True, "searchable": True}
    if raw_type in _DEPARTMENT_TYPES:
        return {"type": "related_list", "relate_type": "department", "lazy": True, "searchable": True}
    return None


def _option_values(item: dict[str, Any], extend: dict[str, Any]) -> list[dict[str, Any]]:
    options = (
        extend.get("options")
        or extend.get("option")
        or item.get("options")
        or item.get("option_values")
        or item.get("values")
        or []
    )
    if not isinstance(options, list):
        return []
    result: list[dict[str, Any]] = []
    for option in options:
        if isinstance(option, dict):
            label = option.get("label") or option.get("name") or option.get("text") or option.get("value")
            value = option.get("value", option.get("id", label))
            disabled = bool(option.get("disabled"))
            meta = {key: value for key, value in option.items() if key not in {"label", "name", "text", "value", "disabled"}}
        else:
            label, value, disabled, meta = option, option, False, {}
        if label not in (None, ""):
            result.append({"label": str(label), "value": value, "disabled": disabled, "meta": meta})
    return result


def _field_key(item: dict[str, Any]) -> str:
    return str(item.get("field_key") or item.get("field_id") or item.get("name") or "").strip()


def _field_label(item: dict[str, Any]) -> str:
    return str(item.get("field_name") or item.get("label") or item.get("title") or "").strip()


def _node_handle(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, list):
        handles = [item for item in value if isinstance(item, dict)]
        return next((item for item in handles if item.get("type") == "submitter_choice"), handles[0] if handles else {})
    return {}


def _assignees(handle: dict[str, Any]) -> list[dict[str, Any]]:
    source = handle.get("relate_id") if int(handle.get("is_all_company") or 0) == 2 else handle.get("relate_user")
    source = source if isinstance(source, list) else []
    result: dict[str, dict[str, Any]] = {}
    for item in source:
        if not isinstance(item, dict):
            continue
        uid = str(item.get("uid") or item.get("id") or item.get("relate_id") or "").strip()
        name = str(item.get("display_name") or item.get("name") or item.get("relate_name") or "").strip()
        if uid and name:
            result[uid] = {"uid": uid, "name": name, "avatar": item.get("avatar")}
    return list(result.values())


def _numeric_uid(value: Any) -> int | str:
    text = str(value)
    return int(text) if text.isdigit() else text

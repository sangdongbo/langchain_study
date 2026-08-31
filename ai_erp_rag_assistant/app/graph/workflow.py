from __future__ import annotations

import re
import json
from datetime import date, datetime, time
from hashlib import sha256
from typing import Any
from uuid import uuid4

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ai_erp_rag_assistant.app.graph.state import ErpRagState
from ai_erp_rag_assistant.app.services.approval_form_service import (
    build_form_schema,
    build_submit_nodes,
    missing_assignee_nodes,
    normalize_approval_nodes,
)
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event
from ai_erp_rag_assistant.app.services.model_service import model_service
from ai_erp_rag_assistant.app.tools.erp_tools import (
    get_current_user,
    get_approval_nodes,
    get_approval_template,
    list_approval_templates,
    query_approval_status,
    submit_approval,
)
from ai_erp_rag_assistant.app.tools.rag_tools import search_knowledge


def _record(state: ErpRagState, tool: str, **data: Any) -> list[dict[str, Any]]:
    calls = list(state.get("tool_calls", []))
    calls.append({"tool": tool, **data})
    write_audit_event(
        "workflow.tool",
        {
            "tool": tool,
            "session_id": state.get("session_id"),
            "company_id": state.get("company_id") or state.get("user_context", {}).get("company_id"),
            "user_id": state.get("user_id"),
            "data": data,
        },
    )
    return calls


def _has_value(value: Any) -> bool:
    return value not in (None, "", [], {})


def _parse_temporal(value: Any) -> date | datetime | time | None:
    value = _actual_value(value)
    if isinstance(value, (date, datetime, time)):
        return value
    text = str(value).strip().replace("Z", "+00:00")
    for parser in (datetime.fromisoformat, date.fromisoformat, time.fromisoformat):
        try:
            return parser(text)
        except ValueError:
            continue
    return None


def _actual_value(value: Any) -> Any:
    if isinstance(value, dict) and "value" in value:
        return value.get("value")
    return value


def _validate_fields(template: dict[str, Any], fields: dict[str, Any]) -> tuple[list[str], list[str]]:
    missing: list[str] = []
    invalid: list[str] = []
    for field in template.get("fields", []):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        label = str(field.get("label") or name)
        value = fields.get(name)
        if field.get("required") and not _has_value(value):
            missing.append(label)
            continue
        if not _has_value(value):
            continue
        actual_value = _actual_value(value)
        options = [str(option) for option in field.get("options", []) if option is not None]
        option_values = [
            str(option.get("value"))
            for option in field.get("option_values", [])
            if isinstance(option, dict) and option.get("value") is not None
        ]
        submitted_values = actual_value if isinstance(actual_value, list) else [actual_value]
        if options and any(str(item) not in {*options, *option_values} for item in submitted_values):
            invalid.append(f"{label}必须是：{'、'.join(options)}")
            continue
        field_type = str(field.get("type") or "").lower()
        semantic_type = f"{name.lower()} {field_type}"
        if any(token in semantic_type for token in ("datetime", "date_time", "start_time", "end_time")):
            if not isinstance(_parse_temporal(value), datetime):
                invalid.append(f"{label}必须是完整日期时间")
        elif "date" in semantic_type:
            if not isinstance(_parse_temporal(value), (date, datetime)):
                invalid.append(f"{label}必须是有效日期")
        elif "time" in semantic_type:
            if not isinstance(_parse_temporal(value), (time, datetime)):
                invalid.append(f"{label}必须是有效时间")
        elif any(token in field_type for token in ("number", "integer", "float", "decimal")):
            try:
                float(actual_value)
            except (TypeError, ValueError):
                invalid.append(f"{label}必须是数字")

    start_keys = [key for key in fields if any(token in key.lower() for token in ("start", "begin"))]
    end_keys = [key for key in fields if any(token in key.lower() for token in ("end", "finish"))]
    if start_keys and end_keys:
        start_value = _parse_temporal(fields[start_keys[0]])
        end_value = _parse_temporal(fields[end_keys[0]])
        if start_value is not None and end_value is not None:
            try:
                if start_value >= end_value:
                    invalid.append("结束时间必须晚于开始时间")
            except TypeError:
                invalid.append("开始时间与结束时间格式必须一致")
    return missing, invalid


def _validation_contract(
    template: dict[str, Any],
    fields: dict[str, Any],
    invalid_messages: list[str],
) -> tuple[list[str], list[dict[str, str]]]:
    missing_keys: list[str] = []
    invalid_fields: list[dict[str, str]] = []
    for field in template.get("fields", []):
        if not isinstance(field, dict):
            continue
        key = str(field.get("name") or "")
        label = str(field.get("label") or key)
        if field.get("required") and not _has_value(fields.get(key)):
            missing_keys.append(key)
        for message in invalid_messages:
            if message.startswith(label) or (
                "开始时间" in message and any(marker in key.lower() for marker in ("start", "begin"))
            ) or (
                "结束时间" in message and any(marker in key.lower() for marker in ("end", "finish"))
            ):
                item = {"field_key": key, "message": message}
                if item not in invalid_fields:
                    invalid_fields.append(item)
    return missing_keys, invalid_fields


def _select_candidate_id(message: str, candidates: list[dict[str, Any]]) -> str:
    cleaned = message.strip()
    if cleaned.isdigit():
        index = int(cleaned)
        if 1 <= index <= len(candidates):
            return str(candidates[index - 1].get("template_id") or "")
    for item in candidates:
        markers = (
            str(item.get("template_id") or ""),
            str(item.get("title") or ""),
        )
        if any(marker and marker in cleaned for marker in markers):
            return str(item.get("template_id") or "")
    return ""


def _submission_fields(template: dict[str, Any], fields: dict[str, Any]) -> dict[str, Any]:
    """Convert display labels back to ERP option values for getNodes/add."""
    result = dict(fields)
    for field in template.get("fields", []):
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "")
        value = result.get(name)
        if not name or value in (None, ""):
            continue
        for option in field.get("option_values", []):
            if not isinstance(option, dict):
                continue
            if str(option.get("label")) == str(value):
                result[name] = option.get("value")
                break
    return result


def _extract_dynamic_option_fields(
    message: str,
    template_fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind option words in the message to the real dynamic ERP field keys.

    The planner may understand "病假" but call it ``leave_type`` while ERP
    exposes ``rest_holiday_rule_id``.  Matching against the template's live
    option metadata keeps template IDs and field keys fully dynamic and also
    supports labels such as "病假（余10天）".
    """
    normalized_message = _compact_match_text(message)
    if not normalized_message:
        return {}

    result: dict[str, Any] = {}
    for field in template_fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        option_labels = _field_option_labels(field)
        if not option_labels:
            continue

        exact_matches: list[str] = []
        core_matches: list[str] = []
        for label in option_labels:
            normalized_label = _compact_match_text(label)
            if len(normalized_label) >= 2 and normalized_label in normalized_message:
                exact_matches.append(label)
                continue
            for marker in _option_core_markers(label):
                if len(marker) >= 2 and marker in normalized_message:
                    core_matches.append(label)
                    break

        matches = exact_matches or core_matches
        unique_matches = list(dict.fromkeys(matches))
        if len(unique_matches) == 1:
            result[name] = unique_matches[0]
    return result


def _extract_dynamic_duration_fields(
    message: str,
    template_fields: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind natural duration phrases to the ERP's real duration field.

    ERP exposes leave duration as a numeric field such as ``rest_duration``.
    Users naturally say "半天" instead of naming that field, so a generic
    planner key such as ``duration`` would otherwise be filtered out before
    validation.
    """
    value = _duration_value_from_text(message)
    if value is None:
        return {}

    result: dict[str, Any] = {}
    for field in template_fields:
        if not isinstance(field, dict):
            continue
        name = str(field.get("name") or "").strip()
        if not name:
            continue
        label = str(field.get("label") or "")
        erp_field_type = str(field.get("erp_field_type") or "").lower()
        semantic = f"{name.lower()} {label} {erp_field_type}"
        if "duration" in semantic or "时长" in semantic:
            result[name] = value
    return result


def _duration_value_from_text(message: str) -> int | float | None:
    compact = _compact_match_text(message)
    if not compact:
        return None
    if "半天" in compact or "半日" in compact:
        return 0.5
    if "全天" in compact:
        return 1

    numeric = re.search(r"(?<![\d.])(\d+(?:\.\d+)?)(?:个)?(?:天|日|小时)", compact)
    if numeric:
        value = float(numeric.group(1))
        return int(value) if value.is_integer() else value

    chinese = re.search(r"([一二两三四五六七八九十]+)(?:个)?(?:天|日|小时)", compact)
    if chinese:
        return _small_chinese_number(chinese.group(1))
    return None


def _small_chinese_number(value: str) -> int | None:
    digits = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
    if value in digits:
        return digits[value]
    if value == "十":
        return 10
    if "十" in value:
        tens_text, ones_text = value.split("十", 1)
        tens = digits.get(tens_text, 1) if tens_text else 1
        ones = digits.get(ones_text, 0) if ones_text else 0
        return tens * 10 + ones
    return None


def _field_option_labels(field: dict[str, Any]) -> list[str]:
    labels: list[str] = []
    for option in field.get("option_values", []):
        if isinstance(option, dict):
            label = str(option.get("label") or "").strip()
            if label:
                labels.append(label)
    for option in field.get("options", []):
        label = str(option or "").strip()
        if label:
            labels.append(label)
    return list(dict.fromkeys(labels))


def _option_core_markers(label: str) -> list[str]:
    core = str(label or "").strip()
    for marker in ("（", "(", "【", "["):
        if marker in core:
            core = core.split(marker, 1)[0].strip()
            break
    markers = [_compact_match_text(core)] if core else []
    # ERP often labels the option "调休假" while users naturally say "调休".
    if core.endswith("假") and len(core) > 2:
        markers.append(_compact_match_text(core[:-1]))
    return list(dict.fromkeys(marker for marker in markers if marker))


def _compact_match_text(value: Any) -> str:
    return "".join(str(value or "").lower().split())


def _explicit_template_change(message: str) -> bool:
    return any(marker in message for marker in ("改成", "换成", "切换到", "改为", "另一个审批", "重新申请"))


def _explicit_field_change(message: str) -> bool:
    return any(marker in message for marker in ("改成", "换成", "改为", "修改", "调整", "重新填写"))


def _is_confirmation_message(message: str) -> bool:
    compact = _compact_match_text(message).strip("，。,.!！")
    return compact in {"确认", "确认提交", "同意提交", "提交", "提交申请"}


def _has_frozen_preview_confirmation(state: ErpRagState) -> bool:
    preview = state.get("preview", {})
    return bool(
        state.get("active_approval")
        and preview
        and preview.get("requires_confirmation", True)
        and not _explicit_field_change(state.get("user_message", ""))
        and (state.get("confirm") is True or _is_confirmation_message(state.get("user_message", "")))
    )


def _route_from_start(state: ErpRagState) -> str:
    return "frozen_confirmation" if _has_frozen_preview_confirmation(state) else "planner"


def accept_frozen_preview_confirmation(state: ErpRagState) -> ErpRagState:
    """Turn an explicit confirmation into a command without re-running the LLM."""
    return {
        "route": "approval_workflow",
        "confirm": True,
        "pending_question": "",
        "workflow_status": "preview_ready",
        "tool_calls": _record(
            state,
            "workflow.preview_confirmed",
            preview_id=state.get("preview", {}).get("preview_id"),
            preview_version=state.get("preview", {}).get("preview_version"),
        ),
    }


def agent_planner(state: ErpRagState) -> ErpRagState:
    previous_plan = dict(state.get("plan", {}))
    active_approval = bool(state.get("active_approval"))
    context = {
        "pending_question": state.get("pending_question", ""),
        "pending_preview": state.get("preview", {}),
        "collected_fields": state.get("fields", {}),
        "confirm_requested": state.get("confirm"),
        "active_approval": active_approval,
        "previous_approval_type": previous_plan.get("approval_type", ""),
        "template_fields": state.get("template", {}).get("fields", []),
    }
    plan = model_service.plan(state["user_message"], context=context)
    if active_approval and not _explicit_template_change(state["user_message"]):
        # During field collection, words such as "事假" are field values, not
        # a request to search the template catalog again.
        plan.approval_type = ""
    if active_approval and (
        plan.route == "general_chat"
        or plan.decision in {"confirm", "cancel"}
        or state.get("confirm") is True
    ):
        plan.route = "approval_workflow"
    if plan.decision == "confirm":
        state["confirm"] = True
    active_approval = active_approval or plan.route == "approval_workflow"
    return {
        "route": plan.route,
        "plan": plan.model_dump(),
        "fields": {**state.get("fields", {}), **plan.fields},
        "confirm": state.get("confirm"),
        "active_approval": active_approval,
        "tool_calls": _record(state, "llm.agent_planner", plan=plan.model_dump()),
    }


def load_erp_context(state: ErpRagState) -> ErpRagState:
    user = state.get("user_context", {})
    reused = bool(user.get("company_id") and user.get("erp_mode"))
    if not reused:
        user = get_current_user(
            state["user_id"],
            uid=state.get("uid", ""),
            authorization=state.get("authorization", ""),
            company_id=state.get("company_id", ""),
            department=state.get("department", ""),
        )
    return {
        "user_context": user,
        "tool_calls": _record(
            state,
            "erp.get_current_user",
            mode=user.get("erp_mode"),
            company_id=user.get("company_id"),
            department=user.get("department"),
            reused=reused,
        ),
    }


def retrieve_rag(state: ErpRagState) -> ErpRagState:
    user = state["user_context"]
    permissions = user.get("permissions") or user.get("permission_tags") or []
    evidence = search_knowledge(
        state.get("plan", {}).get("query") or state["user_message"],
        company_id=str(user.get("company_id", "")),
        department=str(user.get("department", "")),
        permission_tags=[str(item) for item in permissions if item],
    )
    return {
        "evidence": evidence,
        "tool_calls": _record(
            state,
            "rag.milvus.search",
            collection="erp_knowledge_chunks",
            result_count=len(evidence),
        ),
    }


def query_erp_status_node(state: ErpRagState) -> ErpRagState:
    data = query_approval_status(state["user_id"], user=state.get("user_context", {}))
    return {
        "erp_data": data,
        "tool_calls": _record(state, "erp.approval_status", mode=data.get("erp_mode"), result_keys=list(data.keys())),
    }


def load_approval_template(state: ErpRagState) -> ErpRagState:
    user = state["user_context"]
    planner_type = str(state.get("plan", {}).get("approval_type") or "").strip()
    approval_query = planner_type or (
        str(state.get("template", {}).get("title") or "")
        if state.get("template")
        else state["user_message"]
    )
    existing_template = state.get("template", {})
    candidates = list(state.get("template_candidates", []))
    existing_intent = str(existing_template.get("requested_approval_type") or existing_template.get("title") or "").strip()
    has_existing = bool(existing_template.get("fields") and existing_template.get("template_id"))
    explicit_change = _explicit_template_change(state["user_message"])
    same_intent = has_existing and not explicit_change and (
        not planner_type
        or not existing_intent
        or planner_type in existing_intent
        or existing_intent in planner_type
    )
    if existing_template.get("fields") and existing_template.get("template_id") and same_intent:
        template = dict(existing_template)
        reuse_template = True
    else:
        if not candidates:
            candidates = list_approval_templates(
                approval_query,
                str(user.get("company_id", "")),
                user=user,
            )
        if not candidates:
            question = "没有找到匹配的 ERP 审批模板，请说明要办理的业务类型。"
            return {
                "template_candidates": [],
                "template": {},
                "fields": {},
                "pending_question": question,
                "assistant_message": question,
                "workflow_status": "waiting_user",
                "tool_calls": _record(state, "erp.approval_list", query=approval_query, result_count=0),
            }
        selected_id = _select_candidate_id(state["user_message"], candidates)
        if not selected_id:
            selected_id = model_service.select_template(
                state["user_message"],
                candidates,
                conversation=state.get("conversation", []),
            )
        if not selected_id:
            labels = "、".join(
                f"{index}. {item.get('title') or item.get('template_id')}"
                for index, item in enumerate(candidates[:8], start=1)
            )
            question = "找到多个可能的审批模板，请回复序号或模板名称：" + labels
            return {
                "template_candidates": candidates,
                "template": {},
                "fields": {},
                "pending_question": question,
                "assistant_message": question,
                "workflow_status": "waiting_user",
                "tool_calls": _record(
                    state,
                    "erp.approval_list",
                    query=approval_query,
                    result_count=len(candidates),
                    selection_required=True,
                ),
            }
        selected = next(item for item in candidates if str(item.get("template_id")) == selected_id)
        template = get_approval_template(
            selected_id,
            str(user.get("company_id", "")),
            title=str(selected.get("title") or ""),
            user=user,
        )
        reuse_template = False
    approval_type = str(template.get("title") or approval_query)
    template["requested_approval_type"] = approval_type
    template_changed = bool(existing_template and not reuse_template)
    field_names = {str(item.get("name")) for item in template.get("fields", []) if isinstance(item, dict)}
    previous_fields = {} if template_changed else dict(state.get("fields", {}))
    # Planner fields use generic names and must not leak into the real ERP
    # payload. Preserve only keys that actually exist in the selected template.
    fields = {
        str(name): value
        for name, value in previous_fields.items()
        if str(name) in field_names and _has_value(value)
    }
    fields.update({
        str(name): value
        for name, value in state.get("plan", {}).get("fields", {}).items()
        if str(name) in field_names and _has_value(value)
    })
    matched_option_fields = _extract_dynamic_option_fields(
        state["user_message"],
        template.get("fields", []),
    )
    fields.update(matched_option_fields)
    matched_duration_fields = _extract_dynamic_duration_fields(
        state["user_message"],
        template.get("fields", []),
    )
    fields.update(matched_duration_fields)
    extracted_fields: dict[str, Any] = {}
    extraction_error = ""
    if state.get("plan", {}).get("decision") == "continue":
        try:
            extracted_fields = model_service.extract_approval_fields(
                state["user_message"],
                approval_type=approval_type,
                template_title=str(template.get("title") or ""),
                template_fields=template.get("fields", []),
                known_fields=fields,
                pending_question=state.get("pending_question", ""),
                conversation=state.get("conversation", []),
            )
            fields.update(extracted_fields)
            # Deterministic matches are grounded in the live ERP options and
            # therefore take precedence over a conflicting LLM extraction.
            fields.update(matched_option_fields)
            fields.update(matched_duration_fields)
        except RuntimeError as exc:
            extraction_error = str(exc)
    draft_key = str(state.get("draft_key") or "") if reuse_template else ""
    if not draft_key:
        draft_key = uuid4().hex
    form_schema = build_form_schema(template, fields)
    return {
        "template": template,
        "fields": fields,
        "draft_key": draft_key,
        "form_schema": form_schema,
        "workflow_status": "collecting_fields",
        "tool_calls": _record(
            state,
            "erp.approval_template",
            mode=template.get("erp_mode"),
            template_id=template.get("template_id"),
            field_count=len(template.get("fields", [])),
            reused=reuse_template,
            extracted_fields=sorted(extracted_fields),
            matched_option_fields=sorted(matched_option_fields),
            matched_duration_fields=sorted(matched_duration_fields),
            extraction_error=extraction_error,
            candidates=len(candidates),
        ),
    }


def validate_and_preview(state: ErpRagState) -> ErpRagState:
    if state.get("plan", {}).get("decision") == "cancel":
        return {
            "preview": {},
            "pending_question": "",
            "assistant_message": "已取消当前审批草稿。",
            "fields": {},
            "template": {},
            "template_candidates": [],
            "conversation": [],
            "workflow_status": "cancelled",
            "active_approval": False,
            "tool_calls": _record(state, "erp.cancel_draft", cancelled=True),
        }
    template = state.get("template", {})
    fields = state.get("fields", {})
    if not template.get("template_id"):
        return {
            "preview": {},
            "assistant_message": state.get("assistant_message") or "请先选择一个 ERP 审批模板。",
            "pending_question": state.get("pending_question") or "请先选择一个 ERP 审批模板。",
            "workflow_status": "waiting_user",
            "active_approval": True,
            "tool_calls": _record(state, "erp.validate_fields", valid=False, reason="template_not_selected"),
        }
    missing, invalid = _validate_fields(template, fields)
    missing_field_keys, invalid_fields = _validation_contract(template, fields, invalid)
    form_schema = build_form_schema(
        template,
        fields,
        missing_field_keys=missing_field_keys,
        invalid_fields=invalid_fields,
    )
    if missing or invalid:
        parts: list[str] = []
        if missing:
            parts.append("缺少：" + "、".join(missing))
        if invalid:
            parts.append("需要修正：" + "；".join(invalid))
        question = "请补充或修正以下审批信息：" + "；".join(parts)
        return {
            "pending_question": question,
            "assistant_message": question,
            "preview": {},
            "form_schema": form_schema,
            "workflow_status": "waiting_user",
            "active_approval": True,
            "tool_calls": _record(state, "erp.validate_fields", valid=False, missing=missing, invalid=invalid),
        }
    existing_preview = state.get("preview", {})
    submission_fields = _submission_fields(template, fields)
    nodes: list[dict[str, Any]] = []
    node_error = ""
    template_id = str(template.get("template_id") or "")
    user = state.get("user_context", {})
    if template_id.isdigit() and user.get("uid") and user.get("authorization"):
        try:
            nodes = get_approval_nodes(template_id, submission_fields, user=user)
        except RuntimeError as exc:
            node_error = str(exc)
    approval_flow = normalize_approval_nodes(nodes)
    selected_assignees = dict(state.get("selected_assignees", {}))
    missing_assignee_node_ids = missing_assignee_nodes(approval_flow, selected_assignees)
    submit_nodes = build_submit_nodes(nodes, selected_assignees)
    preview_hash = _preview_hash(template.get("template_id"), submission_fields, submit_nodes)
    same_preview = bool(
        existing_preview
        and (
            existing_preview.get("preview_hash") == preview_hash
            or (
                not existing_preview.get("preview_hash")
                and existing_preview.get("fields") == fields
                and existing_preview.get("template_id") == template.get("template_id")
            )
        )
    )
    previous_version = int(existing_preview.get("preview_version") or 0)
    preview = {
        "preview_id": existing_preview.get("preview_id") if same_preview else uuid4().hex,
        "preview_version": previous_version if same_preview and previous_version else previous_version + 1,
        "preview_hash": preview_hash,
        "template_code": template.get("template_code"),
        "template_id": template.get("template_id"),
        "title": template.get("title") or "请假审批",
        "fields": fields,
        "submission_fields": submission_fields,
        "nodes": nodes,
        "submit_nodes": submit_nodes,
        "approval_flow": approval_flow,
        "selected_assignees": selected_assignees,
        "missing_assignee_node_ids": missing_assignee_node_ids,
        "form_schema": form_schema,
        "requires_confirmation": not missing_assignee_node_ids and not node_error,
        "idempotency_key": existing_preview.get("idempotency_key") if same_preview else uuid4().hex,
    }
    if missing_assignee_node_ids:
        question = "表单字段已补齐，请在审批流程中选择审批人后再确认提交。"
        return {
            "preview": preview,
            "form_schema": form_schema,
            "pending_question": question,
            "assistant_message": question,
            "workflow_status": "waiting_assignee",
            "active_approval": True,
            "tool_calls": _record(
                state,
                "erp.validate_assignees",
                valid=False,
                missing_node_ids=missing_assignee_node_ids,
            ),
        }
    if node_error:
        question = f"表单字段已补齐，但审批流程加载失败：{node_error}"
        return {
            "preview": preview,
            "form_schema": form_schema,
            "pending_question": question,
            "assistant_message": question,
            "workflow_status": "waiting_erp",
            "active_approval": True,
            "tool_calls": _record(state, "erp.approval_nodes", valid=False, error=node_error),
        }
    return {
        "preview": preview,
        "form_schema": form_schema,
        "pending_question": "",
        "assistant_message": "字段已补齐，已生成审批预览。请回复“确认提交”或“取消”。",
        "workflow_status": "preview_ready",
        "active_approval": True,
        "tool_calls": _record(
            state,
            "erp.validate_fields",
            valid=True,
            field_count=len(fields),
            node_count=len(nodes),
            node_error=node_error,
        ),
    }


def submit_if_confirmed(state: ErpRagState) -> ErpRagState:
    if state.get("confirm") is not True or not state.get("preview"):
        return state
    if not state.get("preview", {}).get("requires_confirmation", True):
        message = state.get("pending_question") or "当前审批预览尚未满足提交条件，请先补齐页面提示的信息。"
        return {
            "assistant_message": message,
            "pending_question": message,
            "confirm": None,
            "workflow_status": state.get("workflow_status") or "waiting_user",
            "active_approval": True,
            "tool_calls": _record(state, "workflow.preview_not_submittable"),
        }
    mismatch = _confirmation_mismatch(state)
    if mismatch:
        return {
            "assistant_message": mismatch,
            "pending_question": mismatch,
            "confirm": None,
            "workflow_status": "preview_ready",
            "active_approval": True,
            "tool_calls": _record(state, "workflow.preview_confirmation_rejected", reason=mismatch),
        }
    result = submit_approval(state["preview"], user=state.get("user_context", {}))
    write_mode = str(result.get("erp_write_mode") or "")
    if write_mode == "disabled":
        message = "当前配置禁止写入 ERP，本次确认未提交且已结束，不需要重复确认。"
        closed_preview = {
            **state.get("preview", {}),
            "requires_confirmation": False,
            "confirmation_status": "write_disabled",
        }
        return {
            "erp_data": result,
            "assistant_message": message,
            "consumed_preview": closed_preview,
            # Keep the exact preview visible in this response, but close the
            # draft so the same confirmation cannot be consumed repeatedly.
            "preview": closed_preview,
            "fields": {},
            "template": {},
            "template_candidates": [],
            "conversation": [],
            "pending_question": "",
            "confirm": None,
            "workflow_status": "blocked",
            "active_approval": False,
            "tool_calls": _record(state, "erp.approval_submit", mode=result.get("erp_mode"), result=result),
        }
    else:
        message = f"已完成提交：{result.get('approval_id') or result.get('message') or '请查看 ERP 返回结果'}。"
    return {
        "erp_data": result,
        "assistant_message": message,
        "consumed_preview": dict(state.get("preview", {})),
        "preview": {},
        "fields": {},
        "template": {},
        "template_candidates": [],
        "conversation": [],
        "pending_question": "",
        "confirm": None,
        "workflow_status": "submitted",
        "active_approval": False,
        "tool_calls": _record(state, "erp.approval_submit", mode=result.get("erp_mode"), result=result),
    }


def answer_with_llm(state: ErpRagState) -> ErpRagState:
    route = state.get("route", "general_chat")
    if route == "approval_workflow":
        return state
    message = model_service.answer(
        state["user_message"],
        route=route,
        evidence=state.get("evidence"),
        erp_data=state.get("erp_data"),
    )
    return {
        "assistant_message": message,
        "tool_calls": _record(state, "llm.answer", route=route),
    }


def handle_error(state: ErpRagState, error: Exception) -> ErpRagState:
    message = f"执行失败：{error}"
    return {
        "assistant_message": message,
        "errors": [*state.get("errors", []), str(error)],
        "workflow_status": "failed",
        "tool_calls": _record(state, "system.error", error=str(error)),
    }


def _preview_hash(template_id: Any, submission_fields: dict[str, Any], nodes: list[dict[str, Any]]) -> str:
    payload = json.dumps(
        {"template_id": template_id, "submission_fields": submission_fields, "nodes": nodes},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    )
    return sha256(payload.encode("utf-8")).hexdigest()


def _confirmation_mismatch(state: ErpRagState) -> str:
    preview = state.get("preview", {})
    checks = (
        (state.get("confirm_preview_id"), preview.get("preview_id"), "预览标识"),
        (state.get("confirm_preview_version"), preview.get("preview_version"), "预览版本"),
        (state.get("confirm_preview_hash"), preview.get("preview_hash"), "预览内容"),
    )
    for requested, current, label in checks:
        if requested not in (None, "") and str(requested) != str(current):
            return f"{label}已变化，请查看并确认最新审批预览。"
    return ""


def _route_after_erp_context(state: ErpRagState) -> str:
    if (
        state.get("route") == "approval_workflow"
        and state.get("confirm") is True
        and state.get("preview")
    ):
        # Confirmation applies to the already displayed snapshot. Reloading
        # the template or rebuilding the preview here could change what the
        # user is about to submit and can re-open a closed confirmation loop.
        return "approval_submit"
    return str(state.get("route") or "general_chat")


def create_workflow(*, with_checkpointer: bool = True):
    builder = StateGraph(ErpRagState)
    builder.add_node("agent_planner", agent_planner)
    builder.add_node("accept_frozen_preview_confirmation", accept_frozen_preview_confirmation)
    builder.add_node("load_erp_context", load_erp_context)
    builder.add_node("retrieve_rag", retrieve_rag)
    builder.add_node("query_erp_status", query_erp_status_node)
    builder.add_node("load_approval_template", load_approval_template)
    builder.add_node("validate_and_preview", validate_and_preview)
    builder.add_node("submit_if_confirmed", submit_if_confirmed)
    builder.add_node("answer_with_llm", answer_with_llm)
    builder.add_conditional_edges(
        START,
        _route_from_start,
        {
            "planner": "agent_planner",
            "frozen_confirmation": "accept_frozen_preview_confirmation",
        },
    )
    builder.add_edge("accept_frozen_preview_confirmation", "load_erp_context")
    builder.add_conditional_edges(
        "agent_planner",
        lambda state: state["route"],
        {
            "knowledge": "load_erp_context",
            "erp_status": "load_erp_context",
            "approval_workflow": "load_erp_context",
            "general_chat": "answer_with_llm",
        },
    )
    builder.add_conditional_edges(
        "load_erp_context",
        _route_after_erp_context,
        {
            "knowledge": "retrieve_rag",
            "erp_status": "query_erp_status",
            "approval_workflow": "load_approval_template",
            "approval_submit": "submit_if_confirmed",
        },
    )
    builder.add_edge("retrieve_rag", "answer_with_llm")
    builder.add_edge("query_erp_status", "answer_with_llm")
    builder.add_edge("load_approval_template", "validate_and_preview")
    builder.add_conditional_edges(
        "validate_and_preview",
        lambda state: "submit" if state.get("confirm") is True and state.get("preview") else "end",
        {"submit": "submit_if_confirmed", "end": END},
    )
    builder.add_edge("submit_if_confirmed", END)
    builder.add_edge("answer_with_llm", END)
    if with_checkpointer:
        return builder.compile(checkpointer=MemorySaver())
    return builder.compile()

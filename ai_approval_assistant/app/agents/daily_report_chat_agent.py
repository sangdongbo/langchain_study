from __future__ import annotations

from copy import deepcopy

from app.agents.daily_report_common import (
    preview_message,
    report_date_from_state,
    submit_if_confirmed,
    user_from_daily_report_state,
)
from app.graph.extractors import is_confirm_message
from app.graph.state import ApprovalState
from app.services.daily_report_service import daily_report_service


def daily_report_chat_agent_node(state: ApprovalState) -> ApprovalState:
    """日报 Agent：加载草稿和自定义字段，整理内容后等待用户确认提交。"""
    trace = [*state.get("trace", []), "daily_report_chat_agent"]
    current_state = {**state, "trace": trace}

    submitted = submit_if_confirmed(current_state, daily_report_service)
    if submitted is not None:
        return submitted

    if current_state.get("status") == "awaiting_daily_report_confirmation":
        return _modify_confirmation_content(current_state)

    if current_state.get("awaiting_field") == "daily_report_content":
        return _preview_with_followup_content(current_state)

    user = user_from_daily_report_state(current_state)
    report_type = int(current_state.get("daily_report_type") or 1)
    report_date = report_date_from_state(current_state)
    context = daily_report_service.load_context(user, report_type, report_date)
    payload = deepcopy(context.default_payload)
    explicit_content = _explicit_daily_report_content(current_state.get("user_message", ""))
    if explicit_content:
        payload["content"] = explicit_content
    if not str(payload.get("content") or "").strip():
        return _ask_for_daily_report_content(current_state, payload)
    daily_report_service.save_draft_payload(user, payload)
    preview = daily_report_service.preview_from_payload(payload)
    return {
        **current_state,
        "awaiting_field": None,
        "status": "awaiting_daily_report_confirmation",
        "daily_report_payload": payload,
        "daily_report_preview": preview,
        "assistant_message": preview_message(payload, preview),
        "_route": "end",
    }


def _preview_with_followup_content(state: ApprovalState) -> ApprovalState:
    payload = deepcopy(state.get("daily_report_payload") or {})
    payload["content"] = state.get("user_message", "").strip()
    if not str(payload.get("content") or "").strip():
        return _ask_for_daily_report_content(state, payload)
    daily_report_service.save_draft_payload(user_from_daily_report_state(state), payload)
    preview = daily_report_service.preview_from_payload(payload)
    return {
        **state,
        "status": "awaiting_daily_report_confirmation",
        "awaiting_field": None,
        "daily_report_payload": payload,
        "daily_report_preview": preview,
        "assistant_message": preview_message(payload, preview),
        "_route": "end",
    }


def _modify_confirmation_content(state: ApprovalState) -> ApprovalState:
    payload = deepcopy(state.get("daily_report_payload") or {})
    content = _content_from_answer(state.get("_answer")) or _modify_content_from_message(
        state.get("user_message", "")
    )
    if not content:
        return {
            **state,
            "assistant_message": "可以继续说明要修改的工作内容，或回复“确认提交”。",
            "_route": "end",
        }
    payload["content"] = content
    if not str(payload.get("content") or "").strip():
        return _ask_for_daily_report_content(state, payload)
    daily_report_service.save_draft_payload(user_from_daily_report_state(state), payload)
    preview = daily_report_service.preview_from_payload(payload)
    return {
        **state,
        "status": "awaiting_daily_report_confirmation",
        "awaiting_field": None,
        "daily_report_payload": payload,
        "daily_report_preview": preview,
        "assistant_message": preview_message(payload, preview),
        "_route": "end",
    }


def _ask_for_daily_report_content(
    state: ApprovalState, payload: dict
) -> ApprovalState:
    return {
        **state,
        "status": "collecting",
        "awaiting_field": "daily_report_content",
        "daily_report_payload": payload,
        "assistant_message": "今天还没有可提交的工作内容，请补充日志的工作内容。",
        "_route": "end",
    }


def _explicit_daily_report_content(message: str) -> str:
    text = message.strip()
    if is_confirm_message(text):
        return ""
    for separator in ("：", ":"):
        if separator in text:
            prefix, content = text.split(separator, 1)
            if _looks_like_daily_report_command(prefix):
                return content.strip()
    return ""


def _content_from_answer(answer) -> str:
    if not isinstance(answer, dict):
        return ""
    if answer.get("field_key") != "daily_report_content":
        return ""
    return str(answer.get("value") or answer.get("label") or "").strip()


def _modify_content_from_message(message: str) -> str:
    text = message.strip()
    if is_confirm_message(text):
        return ""
    for marker in ("工作内容改成", "工作内容改为", "内容改成", "内容改为", "改成", "改为"):
        if marker in text:
            return text.split(marker, 1)[1].strip(" ：:")
    return ""


def _looks_like_daily_report_command(text: str) -> bool:
    return any(marker in text for marker in ("写日报", "写日志", "填日报", "填日志"))

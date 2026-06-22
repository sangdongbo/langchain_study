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
        if _is_modify_date_action(current_state):
            return _ask_for_daily_report_date(current_state)
        if _is_modify_action(current_state):
            return _ask_for_daily_report_content(
                current_state,
                deepcopy(current_state.get("daily_report_payload") or {}),
                message="请修改日志的工作内容，提交后我会重新给你确认。",
            )
        return _modify_confirmation_content(current_state)

    if current_state.get("awaiting_field") == "daily_report_content":
        return _preview_with_followup_content(current_state)

    if current_state.get("awaiting_field") == "daily_report_date":
        return _reload_with_followup_date(current_state)

    return _load_daily_report_for_state(current_state)


def _load_daily_report_for_state(state: ApprovalState) -> ApprovalState:
    user = user_from_daily_report_state(state)
    report_type = int(state.get("daily_report_type") or 1)
    report_date = report_date_from_state(state)
    context = daily_report_service.load_context(user, report_type, report_date)
    payload = deepcopy(context.default_payload)
    explicit_content = _explicit_daily_report_content(state.get("user_message", ""))
    if explicit_content:
        payload["content"] = explicit_content
    if not str(payload.get("content") or "").strip():
        return _ask_for_daily_report_content(state, payload)
    daily_report_service.save_draft_payload(user, payload)
    preview = daily_report_service.preview_from_payload(payload)
    return {
        **state,
        "awaiting_field": None,
        "status": "awaiting_daily_report_confirmation",
        "daily_report_date": payload.get("date") or report_date,
        "daily_report_payload": payload,
        "daily_report_preview": preview,
        "assistant_message": preview_message(payload, preview),
        "_route": "end",
    }


def _preview_with_followup_content(state: ApprovalState) -> ApprovalState:
    payload = deepcopy(state.get("daily_report_payload") or {})
    payload["content"] = _content_from_answer(state.get("_answer")) or state.get(
        "user_message", ""
    ).strip()
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


def _reload_with_followup_date(state: ApprovalState) -> ApprovalState:
    report_date = _date_from_answer(state.get("_answer")) or state.get(
        "user_message", ""
    ).strip()
    if not report_date:
        return _ask_for_daily_report_date(state)
    return _load_daily_report_for_state(
        {
            **state,
            "daily_report_date": report_date,
            "awaiting_field": None,
        }
    )


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
    state: ApprovalState,
    payload: dict,
    message: str = "今天还没有可提交的工作内容，请补充日志的工作内容。",
) -> ApprovalState:
    return {
        **state,
        "status": "collecting",
        "awaiting_field": "daily_report_content",
        "daily_report_payload": payload,
        "assistant_message": message,
        "_route": "end",
    }


def _ask_for_daily_report_date(
    state: ApprovalState,
    message: str = "请选择要填写日报的日期，我会重新获取当天草稿。",
) -> ApprovalState:
    payload = deepcopy(state.get("daily_report_payload") or {})
    return {
        **state,
        "status": "collecting",
        "awaiting_field": "daily_report_date",
        "daily_report_date": payload.get("date") or state.get("daily_report_date"),
        "daily_report_payload": payload,
        "assistant_message": message,
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


def _date_from_answer(answer) -> str:
    if not isinstance(answer, dict):
        return ""
    if answer.get("field_key") != "daily_report_date":
        return ""
    return str(answer.get("value") or answer.get("label") or "").strip()


def _is_modify_date_action(state: ApprovalState) -> bool:
    answer = state.get("_answer")
    if isinstance(answer, dict) and answer.get("field_key") == "action":
        value = str(answer.get("value") or answer.get("label") or "").strip()
        if value in {"modify_date", "修改日期", "编辑日期", "edit_date"}:
            return True
    return state.get("user_message", "").strip() in {"修改日期", "编辑日期", "改日期"}


def _is_modify_action(state: ApprovalState) -> bool:
    answer = state.get("_answer")
    if isinstance(answer, dict) and answer.get("field_key") == "action":
        value = str(answer.get("value") or answer.get("label") or "").strip()
        if value in {"modify", "修改", "重新编辑", "edit"}:
            return True
    return state.get("user_message", "").strip() in {"修改", "重新编辑", "编辑内容"}


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

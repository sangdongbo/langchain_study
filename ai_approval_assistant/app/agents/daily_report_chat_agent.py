from __future__ import annotations

from copy import deepcopy

from app.agents.daily_report_common import (
    preview_message,
    report_date_from_state,
    submit_if_confirmed,
    user_from_daily_report_state,
)
from app.graph.state import ApprovalState
from app.services.daily_report_service import daily_report_service


def daily_report_chat_agent_node(state: ApprovalState) -> ApprovalState:
    """日报快捷 Agent：用用户当前消息生成简单日报，确认后提交。"""
    trace = [*state.get("trace", []), "daily_report_chat_agent"]
    current_state = {**state, "trace": trace}

    submitted = submit_if_confirmed(current_state, daily_report_service)
    if submitted is not None:
        return submitted

    user = user_from_daily_report_state(current_state)
    report_type = int(current_state.get("daily_report_type") or 1)
    report_date = report_date_from_state(current_state)
    context = daily_report_service.load_context(user, report_type, report_date)
    payload = deepcopy(context.default_payload)
    payload["content"] = current_state.get("user_message", "").strip()
    preview = daily_report_service.preview_from_payload(payload)
    return {
        **current_state,
        "status": "awaiting_daily_report_confirmation",
        "daily_report_payload": payload,
        "daily_report_preview": preview,
        "assistant_message": preview_message(payload, preview),
        "_route": "end",
    }

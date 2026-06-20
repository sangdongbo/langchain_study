from __future__ import annotations

from app.agents.daily_report_common import (
    preview_message,
    report_date_from_state,
    submit_if_confirmed,
    user_from_daily_report_state,
)
from app.graph.state import ApprovalState
from app.services.daily_report_service import daily_report_service


def daily_report_form_agent_node(state: ApprovalState) -> ApprovalState:
    """日报表单 Agent：加载页面上下文，由前端表单收集完整提交 payload。"""
    trace = [*state.get("trace", []), "daily_report_form_agent"]
    current_state = {**state, "trace": trace}

    submitted = submit_if_confirmed(current_state, daily_report_service)
    if submitted is not None:
        return submitted

    answer = current_state.get("_answer")
    if isinstance(answer, dict) and answer.get("field_key") == "__daily_report_form__":
        payload = daily_report_service.payload_from_form_answer(answer)
        preview = daily_report_service.preview_from_payload(payload)
        return {
            **current_state,
            "status": "awaiting_daily_report_confirmation",
            "daily_report_payload": payload,
            "daily_report_preview": preview,
            "assistant_message": preview_message(payload, preview),
            "_route": "end",
        }

    user = user_from_daily_report_state(current_state)
    report_type = int(current_state.get("daily_report_type") or 1)
    report_date = report_date_from_state(current_state)
    context = daily_report_service.load_context(user, report_type, report_date)
    return {
        **current_state,
        "status": "awaiting_daily_report_form",
        "ui_action": {
            "type": "open_daily_report_form",
            "payload": {
                "type": context.report_type,
                "date": context.report_date,
                "form_fields": _form_fields_for_ui(context.form_fields_payload),
                "config": context.config,
                "draft": context.draft,
                "sync_data": context.sync_data,
                "default_payload": context.default_payload,
            },
        },
        "assistant_message": "我已准备好日报填写页面，请在弹出的表单里补充内容和自定义字段。",
        "_route": "end",
    }


def _form_fields_for_ui(form_fields_payload: dict) -> list[dict]:
    data = form_fields_payload.get("data")
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for key in ("fields", "list", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return value
    return []

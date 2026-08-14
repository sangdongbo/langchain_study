from __future__ import annotations

import json

from ai_deep_agents_assistant.app.services.daily_report_service import (
    daily_report_service,
)
from ai_deep_agents_assistant.app.services.request_context import (
    get_erp_request_context,
)


def get_current_daily_report_date() -> str:
    """返回由后端计算的当前日报日期。"""
    return json.dumps({"date": daily_report_service.current_date()}, ensure_ascii=False)


def collect_daily_report_draft(
    message: str,
    existing_payload_json: str = "{}",
) -> str:
    """收集日报日期和内容，并返回下一个问题或预览。"""
    try:
        existing_payload = json.loads(existing_payload_json) if existing_payload_json else {}
    except json.JSONDecodeError:
        existing_payload = {}
    draft = daily_report_service.build_draft(
        message,
        existing_payload,
        user=get_erp_request_context(),
    )
    return json.dumps(draft.model_dump(), ensure_ascii=False)


def build_daily_report_preview(payload_json: str) -> str:
    """在必填字段完整后生成日报预览。"""
    payload = json.loads(payload_json)
    preview = daily_report_service.build_preview(payload)
    return json.dumps(preview.model_dump(), ensure_ascii=False)


def submit_daily_report_request(payload_json: str, user_id: str) -> str:
    """提交日报；此工具必须在人工确认环节中断。"""
    payload = json.loads(payload_json)
    user = get_erp_request_context()
    if user.user_id != user_id:
        raise ValueError("日报提交用户与当前登录用户不一致。")
    result = daily_report_service.submit(payload, user)
    return json.dumps(result.model_dump(), ensure_ascii=False)


DAILY_REPORT_TOOLS = [
    get_current_daily_report_date,
    collect_daily_report_draft,
    build_daily_report_preview,
    submit_daily_report_request,
]

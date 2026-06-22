from __future__ import annotations

from datetime import date

from app.graph.extractors import is_confirm_message
from app.graph.state import ApprovalState
from app.schemas.approval import UserContext
from app.services.daily_report_service import DailyReportSubmitError


def user_from_daily_report_state(state: ApprovalState) -> UserContext:
    return UserContext(
        user_id=state.get("user_id", ""),
        name=f"User {state.get('user_id', '')}",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid=state.get("uid"),
        authorization=state.get("authorization"),
    )


def report_date_from_state(state: ApprovalState) -> str:
    return str(state.get("daily_report_date") or date.today().isoformat())


def preview_message(payload: dict, preview: dict) -> str:
    lines = [
        "请确认是否提交日报：",
        "",
        f"- 日志类型：日报",
        f"- 日志时间：{preview.get('date')}",
        f"- 工作内容：{preview.get('content')}",
    ]
    for field in preview.get("fields") or []:
        lines.append(f"- {field.get('label')}：{field.get('value')}")
    lines.extend(["", "回复“确认提交”后我再提交日报。"])
    return "\n".join(lines)


def submit_if_confirmed(state: ApprovalState, service) -> ApprovalState | None:
    if state.get("status") != "awaiting_daily_report_confirmation":
        return None
    if not is_confirm_message(state.get("user_message", "")):
        return None
    user = user_from_daily_report_state(state)
    try:
        result = service.submit_payload(user, state.get("daily_report_payload") or {})
    except DailyReportSubmitError as exc:
        message = str(exc)
        return {
            **state,
            "status": "error",
            "assistant_message": f"日报提交失败：{message}",
            "field_errors": [{"field": "daily_report", "message": message}],
            "trace": [*state.get("trace", []), "submit_daily_report"],
        }
    return {
        **state,
        "status": "daily_report_submitted",
        "daily_report_request_id": result.report_id,
        "assistant_message": f"已提交日报。\n\n- 日报编号：{result.report_id or '无'}\n- 当前状态：{result.status}",
        "trace": [*state.get("trace", []), "submit_daily_report"],
    }

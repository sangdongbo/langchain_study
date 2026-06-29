from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Literal

from app.graph.extractors import is_confirm_message
from app.graph.state import ApprovalState
from app.services.model_service import model_service

DailyReportAction = Literal[
    "start",
    "edit_content",
    "edit_date",
    "confirm_submit",
    "cancel",
    "unknown",
]

logger = logging.getLogger("ai_approval_assistant.daily_report_action")


@dataclass(frozen=True)
class DailyReportActionResult:
    action: DailyReportAction
    route: str
    source: str


class DailyReportActionAgent:
    """识别日报子图下一步动作。"""

    def classify(self, state: ApprovalState) -> DailyReportActionResult:
        # 前端按钮和弹窗回传的 answer 最可靠，优先于自然语言和模型判断。
        answer_action = self._from_structured_answer(state)
        if answer_action:
            return self._result(answer_action, "answer")

        status = state.get("status")
        awaiting_field = state.get("awaiting_field")
        message = state.get("user_message", "")

        # 日报已经提交后进入终态，同一会话里的后续确认/修改按钮都不能再触发提交。
        if status == "daily_report_submitted":
            return DailyReportActionResult(
                action="unknown",
                route="end",
                source="state",
            )
        if status == "awaiting_daily_report_confirmation" and is_confirm_message(message):
            return self._result("confirm_submit", "rule")
        if awaiting_field == "daily_report_content":
            return self._result("edit_content", "state")
        if awaiting_field == "daily_report_date":
            return self._result("edit_date", "state")

        # LLM 只负责兜底识别意图，不直接执行提交或接口请求。
        llm_action = self._from_model(state)
        if llm_action:
            return self._result(llm_action, "llm")

        rule_action = self._from_message(message)
        if rule_action:
            return self._result(rule_action, "rule")

        if status == "awaiting_daily_report_confirmation":
            return self._result("edit_content", "state")
        return self._result("start", "state")

    def _from_structured_answer(self, state: ApprovalState) -> DailyReportAction | None:
        answer = state.get("_answer")
        if not isinstance(answer, dict):
            return None
        field_key = answer.get("field_key")
        value = str(answer.get("value") or answer.get("label") or "").strip()
        if field_key == "action":
            if value in {"confirm", "确认", "确认提交", "submit"}:
                return "confirm_submit"
            if value in {"modify", "修改", "重新编辑", "edit"}:
                return "edit_content"
            if value in {"modify_date", "修改日期", "编辑日期", "edit_date"}:
                return "edit_date"
            if value in {"cancel", "取消"}:
                return "cancel"
        if field_key == "daily_report_content":
            return "edit_content"
        if field_key == "daily_report_date":
            return "edit_date"
        return None

    def _from_model(self, state: ApprovalState) -> DailyReportAction | None:
        if not model_service.is_enabled():
            return None
        try:
            payload = model_service._invoke_json(
                system=(
                    "你是日报流程动作识别器。只输出 JSON。"
                    "action 必须是 start、edit_content、edit_date、confirm_submit、cancel、unknown 之一。"
                ),
                user={
                    "task": "classify_daily_report_action",
                    "status": state.get("status"),
                    "awaiting_field": state.get("awaiting_field"),
                    "user_message": state.get("user_message", ""),
                    "answer": state.get("_answer"),
                    "output_schema": {"action": "string", "reason": "string"},
                },
            )
        except Exception as exc:
            logger.warning("LLM daily report action classification failed: %s", exc)
            return None
        action = payload.get("action")
        if action in {
            "start",
            "edit_content",
            "edit_date",
            "confirm_submit",
            "cancel",
            "unknown",
        }:
            return action
        return None

    def _from_message(self, message: str) -> DailyReportAction | None:
        text = message.strip()
        if is_confirm_message(text):
            return "confirm_submit"
        if text in {"取消", "不提交", "算了"}:
            return "cancel"
        if any(marker in text for marker in ("日期", "时间")) and any(
            marker in text for marker in ("改", "修改", "编辑", "换")
        ):
            return "edit_date"
        if text in {"修改", "重新编辑", "编辑内容"} or any(
            marker in text for marker in ("工作内容改", "内容改", "改成", "改为")
        ):
            return "edit_content"
        return None

    def _result(self, action: DailyReportAction, source: str) -> DailyReportActionResult:
        routes = {
            "start": "collect_date",
            "edit_content": "collect_content",
            "edit_date": "collect_date",
            "confirm_submit": "submit",
            "cancel": "cancel",
            "unknown": "collect_content",
        }
        return DailyReportActionResult(
            action=action,
            route=routes[action],
            source=source,
        )


daily_report_action_agent = DailyReportActionAgent()

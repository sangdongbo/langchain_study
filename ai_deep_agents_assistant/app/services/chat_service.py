from __future__ import annotations

import json
from typing import Any

from langgraph.types import Command

from ai_deep_agents_assistant.app.agents.approval_agent import get_approval_deep_agent
from ai_deep_agents_assistant.app.schemas.chat import ChatRequest, ChatResponse
from ai_deep_agents_assistant.app.services.request_context import (
    reset_erp_request_context,
    set_erp_request_context,
)


class DeepAgentsChatService:
    """Application service that adapts Deep Agents output to the chat API."""

    def run_turn(self, request: ChatRequest) -> ChatResponse:
        """Run one chat turn in a durable Deep Agents thread."""
        approval_deep_agent = get_approval_deep_agent()
        config = {"configurable": {"thread_id": request.session_id}}
        context_token = set_erp_request_context(
            request.user_id,
            request.uid,
            request.authorization,
        )
        try:
            if request.message.strip() == "确认提交":
                result = approval_deep_agent.invoke(
                    Command(resume={"decisions": [{"type": "approve"}]}),
                    config=config,
                )
            else:
                user_content = (
                    f"user_id={request.user_id}\n"
                    f"session_id={request.session_id}\n"
                    f"用户消息：{request.message}"
                )
                result = approval_deep_agent.invoke(
                    {"messages": [{"role": "user", "content": user_content}]},
                    config=config,
                )
        finally:
            reset_erp_request_context(context_token)
        return self._to_response(request, result)

    def _to_response(self, request: ChatRequest, result: dict[str, Any]) -> ChatResponse:
        messages = result.get("messages", [])
        final_message = self._message_content(messages[-1]) if messages else ""
        tool_names: list[str] = []
        for message in messages:
            for call in getattr(message, "tool_calls", None) or []:
                tool_names.append(call.get("name", ""))
            if isinstance(message, dict):
                for call in message.get("tool_calls") or []:
                    tool_names.append(call.get("name", ""))

        interrupt_payload = self._extract_interrupt(result)
        intent = self._intent_from_tools(tool_names)
        daily_report_payload, daily_report_preview = self._daily_report_data(messages)
        daily_report_submit_result = self._daily_report_submit_result(messages)
        request_id = (
            str(daily_report_submit_result["request_id"])
            if daily_report_submit_result.get("request_id") is not None
            else None
        )
        status = "idle"
        if interrupt_payload:
            status = "awaiting_confirmation"
            if not final_message:
                final_message = "日报预览已生成，请明确回复“确认提交”后继续。" if intent == "daily_report" else "审批预览已生成，请明确回复“确认提交”后继续。"
        elif daily_report_submit_result.get("status") == "submitted":
            status = "submitted"
        elif "submit_daily_report_request" in tool_names:
            status = "error"
        elif "submit_approval_request" in tool_names:
            status = "submitted"
        elif {
            "collect_approval_draft",
            "collect_daily_report_draft",
        }.intersection(tool_names):
            status = "collecting"

        return ChatResponse(
            session_id=request.session_id,
            status=status,
            assistant_message=final_message,
            intent=intent,
            daily_report_mode="deep_agent" if intent == "daily_report" else None,
            daily_report_payload=daily_report_payload,
            daily_report_preview=daily_report_preview,
            request_id=request_id,
            trace=tool_names,
            interrupt=interrupt_payload,
        )

    def _intent_from_tools(self, tool_names: list[str]) -> str:
        if any("daily_report" in name for name in tool_names):
            return "daily_report"
        if any("approval" in name or name == "get_current_user_context" for name in tool_names):
            return "approval"
        return "general"

    def _daily_report_data(
        self,
        messages: list[Any],
    ) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
        payload = None
        preview = None
        for message in messages:
            name = getattr(message, "name", None)
            content = self._message_content(message)
            if isinstance(message, dict):
                name = name or message.get("name")
            if name not in {
                "collect_daily_report_draft",
                "build_daily_report_preview",
            }:
                continue
            try:
                data = json.loads(content)
            except (TypeError, json.JSONDecodeError):
                continue
            if name == "collect_daily_report_draft":
                if isinstance(data.get("payload"), dict):
                    payload = data["payload"]
                if isinstance(data.get("preview"), dict):
                    preview = data["preview"]
            elif isinstance(data, dict):
                preview = data
        return payload, preview

    def _daily_report_submit_result(self, messages: list[Any]) -> dict[str, Any]:
        for message in reversed(messages):
            name = getattr(message, "name", None)
            if isinstance(message, dict):
                name = name or message.get("name")
            if name != "submit_daily_report_request":
                continue
            try:
                data = json.loads(self._message_content(message))
            except (TypeError, json.JSONDecodeError):
                continue
            if isinstance(data, dict):
                return data
        return {}

    def _message_content(self, message: Any) -> str:
        if isinstance(message, dict):
            content = message.get("content", "")
        else:
            content = getattr(message, "content", "")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return "".join(str(item) for item in content)
        return str(content or "")

    def _extract_interrupt(self, result: dict[str, Any]) -> dict[str, Any] | None:
        interrupts = result.get("__interrupt__") or result.get("interrupts")
        if not interrupts:
            return None
        return {"raw": str(interrupts)}


chat_service = DeepAgentsChatService()

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
    """将 Deep Agents 输出适配为聊天 API 响应的应用服务。"""

    def run_turn(self, request: ChatRequest) -> ChatResponse:
        """在可持久化的 Deep Agents 会话中执行一轮对话。"""
        # 延迟获取带 MemorySaver 检查点的图实例，避免应用启动时创建模型连接。
        approval_deep_agent = get_approval_deep_agent()
        # 同一 session_id 始终映射到同一 LangGraph 线程，用于保留草稿和人工确认中断点。
        config = {"configurable": {"thread_id": request.session_id}}
        # 将 ERP 凭证保存到当前请求上下文，供日报工具访问，避免传入模型提示词。
        context_token = set_erp_request_context(
            request.user_id,
            request.uid,
            request.authorization,
        )
        try:
            if request.message.strip() == "确认提交":
                # 恢复上一轮因危险提交工具而暂停的图，并批准该次工具调用。
                result = approval_deep_agent.invoke(
                    Command(resume={"decisions": [{"type": "approve"}]}),
                    config=config,
                )
            else:
                # 普通对话携带最小的会话身份信息，供 Agent 选择审批或日报工具。
                user_content = (
                    f"user_id={request.user_id}\n"
                    f"session_id={request.session_id}\n"
                    f"用户消息：{request.message}"
                )
                # 执行新的图节点；工具调用和中断状态会由检查点按线程持久化。
                result = approval_deep_agent.invoke(
                    {"messages": [{"role": "user", "content": user_content}]},
                    config=config,
                )
        finally:
            # 无论图执行成功或抛出异常，都恢复 ContextVar，防止凭证泄漏到其他请求。
            reset_erp_request_context(context_token)
        # 将 LangGraph 原始消息、工具轨迹和中断信息整理为前端聊天响应。
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

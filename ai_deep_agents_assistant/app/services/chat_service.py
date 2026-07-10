from __future__ import annotations

from typing import Any

from langgraph.types import Command

from ai_deep_agents_assistant.app.agents.approval_agent import get_approval_deep_agent
from ai_deep_agents_assistant.app.schemas.chat import ChatRequest, ChatResponse


class DeepAgentsChatService:
    """Application service that adapts Deep Agents output to the chat API."""

    def run_turn(self, request: ChatRequest) -> ChatResponse:
        """Run one chat turn in a durable Deep Agents thread."""
        approval_deep_agent = get_approval_deep_agent()
        config = {"configurable": {"thread_id": request.session_id}}
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
        return self._to_response(request, result)

    def _to_response(self, request: ChatRequest, result: dict[str, Any]) -> ChatResponse:
        messages = result.get("messages", [])
        final_message = messages[-1].content if messages else ""
        tool_names: list[str] = []
        for message in messages:
            for call in getattr(message, "tool_calls", None) or []:
                tool_names.append(call.get("name", ""))

        interrupt_payload = self._extract_interrupt(result)
        status = "idle"
        if "submit_approval_request" in tool_names:
            status = "submitted"
        elif interrupt_payload:
            status = "awaiting_confirmation"
        elif "collect_approval_draft" in tool_names:
            status = "collecting"

        return ChatResponse(
            session_id=request.session_id,
            status=status,
            assistant_message=final_message,
            trace=tool_names,
            interrupt=interrupt_payload,
        )

    def _extract_interrupt(self, result: dict[str, Any]) -> dict[str, Any] | None:
        interrupts = result.get("__interrupt__") or result.get("interrupts")
        if not interrupts:
            return None
        return {"raw": str(interrupts)}


chat_service = DeepAgentsChatService()

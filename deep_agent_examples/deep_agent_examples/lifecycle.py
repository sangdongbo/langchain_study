from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Annotated, Any, NotRequired

from deepagents.graph import DeepAgentState
from langchain.agents.middleware.types import (
    AgentMiddleware,
    ModelRequest,
    ModelResponse,
    ToolCallRequest,
)


def merge_lifecycle_events(
    current: list[str] | None,
    update: list[str],
) -> list[str]:
    """Append events without duplicating state echoed back by a subagent."""
    merged = list(current or [])
    merged.extend(event for event in update if event not in merged)
    return merged


class LifecycleState(DeepAgentState):
    lifecycle_events: Annotated[NotRequired[list[str]], merge_lifecycle_events]
    parent_lifecycle_events: Annotated[NotRequired[list[str]], merge_lifecycle_events]
    child_lifecycle_events: Annotated[NotRequired[list[str]], merge_lifecycle_events]


class LifecycleProbeMiddleware(AgentMiddleware):
    """Expose agent-loop hooks in State and wrapper spans in LangSmith."""

    state_schema = LifecycleState

    def __init__(self, scope: str, field: str = "lifecycle_events") -> None:
        self._scope = scope
        self._field = field

    @property
    def name(self) -> str:
        return f"{self._scope.title()}LifecycleProbe"

    def _event(self, state: dict[str, Any], stage: str) -> dict[str, list[str]]:
        sequence = len(state.get(self._field) or []) + 1
        return {self._field: [f"{sequence:02d} {self._scope}.{stage}"]}

    def before_agent(self, state, runtime):  # noqa: ARG002
        return self._event(state, "before_agent")

    async def abefore_agent(self, state, runtime):  # noqa: ARG002
        return self._event(state, "before_agent")

    def before_model(self, state, runtime):  # noqa: ARG002
        return self._event(state, "before_model")

    async def abefore_model(self, state, runtime):  # noqa: ARG002
        return self._event(state, "before_model")

    def after_model(self, state, runtime):  # noqa: ARG002
        last = state["messages"][-1]
        count = len(getattr(last, "tool_calls", None) or [])
        return self._event(state, f"after_model(tool_calls={count})")

    async def aafter_model(self, state, runtime):  # noqa: ARG002
        return self.after_model(state, runtime)

    def after_agent(self, state, runtime):  # noqa: ARG002
        return self._event(state, "after_agent")

    async def aafter_agent(self, state, runtime):  # noqa: ARG002
        return self._event(state, "after_agent")

    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        return await handler(request)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        return await handler(request)

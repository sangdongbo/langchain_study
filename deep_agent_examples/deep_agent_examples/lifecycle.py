"""用于观察 Agent 生命周期钩子的自定义 State 与 Middleware。

该中间件不改变模型或工具结果，只把各阶段名称写入 State，并通过 wrapper
保留 LangSmith 中的调用层级，便于理解一次 Agent 循环实际经过哪些步骤。
"""

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
    """合并生命周期事件，同时去掉子 Agent 回传 State 中的重复事件。

    该函数作为 LangGraph State reducer 使用。``current`` 是 State 中已有记录，
    ``update`` 是节点本次返回的增量；返回值会重新写回对应 State 字段。
    """
    merged = list(current or [])
    merged.extend(event for event in update if event not in merged)
    return merged


class LifecycleState(DeepAgentState):
    """在 DeepAgentState 基础上增加三组可合并的生命周期事件。"""

    # 单 Agent 示例使用的默认事件列表。
    lifecycle_events: Annotated[NotRequired[list[str]], merge_lifecycle_events]
    # 父子 Agent 示例中，父 Agent 的事件单独写入这里。
    parent_lifecycle_events: Annotated[NotRequired[list[str]], merge_lifecycle_events]
    # 父子 Agent 示例中，子 Agent 的事件单独写入这里。
    child_lifecycle_events: Annotated[NotRequired[list[str]], merge_lifecycle_events]


class LifecycleProbeMiddleware(AgentMiddleware):
    """把 Agent 循环钩子写入 State，并保留模型/工具 wrapper 追踪层级。"""

    # 告诉框架该 Middleware 需要 LifecycleState 中新增的字段。
    state_schema = LifecycleState

    def __init__(self, scope: str, field: str = "lifecycle_events") -> None:
        # scope 用于区分 agent、parent、child；field 决定事件写入哪个 State 列表。
        self._scope = scope
        self._field = field

    @property
    def name(self) -> str:
        """生成 LangGraph/LangSmith 中可辨认的中间件名称。"""
        return f"{self._scope.title()}LifecycleProbe"

    def _event(self, state: dict[str, Any], stage: str) -> dict[str, list[str]]:
        """构造单条带序号的 State 增量，由 reducer 合并到现有事件列表。"""
        sequence = len(state.get(self._field) or []) + 1
        return {self._field: [f"{sequence:02d} {self._scope}.{stage}"]}

    # before_agent：一次 Agent run 开始、进入模型循环之前执行。
    def before_agent(self, state, runtime):  # noqa: ARG002
        return self._event(state, "before_agent")

    # 异步图会调用 a* 版本；记录内容与同步钩子保持一致。
    async def abefore_agent(self, state, runtime):  # noqa: ARG002
        return self._event(state, "before_agent")

    # before_model：每一轮模型调用之前执行，因此工具返回模型后还会再次出现。
    def before_model(self, state, runtime):  # noqa: ARG002
        return self._event(state, "before_model")

    async def abefore_model(self, state, runtime):  # noqa: ARG002
        return self._event(state, "before_model")

    # after_model：模型返回后执行，并记录这一轮生成了多少个工具调用。
    def after_model(self, state, runtime):  # noqa: ARG002
        last = state["messages"][-1]
        count = len(getattr(last, "tool_calls", None) or [])
        return self._event(state, f"after_model(tool_calls={count})")

    async def aafter_model(self, state, runtime):  # noqa: ARG002
        return self.after_model(state, runtime)

    # after_agent：模型给出最终答案、整个 Agent run 即将结束时执行。
    def after_agent(self, state, runtime):  # noqa: ARG002
        return self._event(state, "after_agent")

    async def aafter_agent(self, state, runtime):  # noqa: ARG002
        return self._event(state, "after_agent")

    # wrapper 当前不修改请求/响应，只把调用包进 Middleware span，方便追踪嵌套关系。
    def wrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], ModelResponse],
    ) -> ModelResponse:
        # request 是当前模型请求快照；handler 才是真正执行下一层模型调用的函数。
        return handler(request)

    async def awrap_model_call(
        self,
        request: ModelRequest,
        handler: Callable[[ModelRequest], Awaitable[ModelResponse]],
    ) -> ModelResponse:
        # 异步版本参数含义相同，但 handler 返回 Awaitable，必须 await。
        return await handler(request)

    def wrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Any],
    ) -> Any:
        # request 包含工具名/参数；handler 执行真正工具或下一层 Middleware。
        return handler(request)

    async def awrap_tool_call(
        self,
        request: ToolCallRequest,
        handler: Callable[[ToolCallRequest], Awaitable[Any]],
    ) -> Any:
        # 异步工具包装器必须 await handler，才能保留正确的执行与追踪层级。
        return await handler(request)

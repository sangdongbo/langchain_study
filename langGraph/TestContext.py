from __future__ import annotations

from dataclasses import dataclass
from collections.abc import Sequence
from typing import Any

from langchain.agents import create_agent
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_core.messages import AIMessage, BaseMessage
from langchain_core.outputs import ChatGeneration, ChatResult
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool
from langchain.tools import ToolRuntime, tool


"""LangGraph/LangChain Agent 中 runtime context 的最小示例。

运行方式：
    python langGraph/TestContext.py

这个例子不请求 DeepSeek，也不需要 API Key。重点是：
1. 用 context_schema 声明运行时上下文类型。
2. 在工具参数里使用 ToolRuntime[Context]。
3. 调用 agent.invoke(..., context=Context(...)) 把上下文传进去。
"""


@dataclass
class Context:
    """每次运行时传入的上下文。

    这里用 user_id 模拟登录用户。真实项目里还可以放租户、权限、
    请求来源、语言偏好等不希望模型自己填写的信息。
    """

    user_id: str


USER_PROFILES = {
    "U001": "张三，上海销售",
    "U002": "李四，北京财务",
}


@tool
def get_user_profile(runtime: ToolRuntime[Context]) -> str:
    """读取当前登录用户的资料。"""

    user_id = runtime.context.user_id
    profile = USER_PROFILES.get(user_id, "未知用户")
    return f"当前用户 {user_id}：{profile}。"


class ContextDemoModel(BaseChatModel):
    """离线演示用模型。

    第一次调用时请求执行 get_user_profile 工具，第二次调用时返回最终回答。
    这样可以完整走过 Agent -> ToolRuntime -> context 的路径。
    """

    calls: int = 0

    @property
    def _llm_type(self) -> str:
        return "context-demo-model"

    def bind_tools(
        self,
        tools: Sequence[dict[str, Any] | type | BaseTool | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> Runnable:
        return self

    def _generate(
        self,
        messages: list[BaseMessage],
        stop: list[str] | None = None,
        run_manager: Any | None = None,
        **kwargs: Any,
    ) -> ChatResult:
        self.calls += 1
        if self.calls == 1:
            message = AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "get_user_profile",
                        "args": {},
                        "id": "call-get-user-profile",
                        "type": "tool_call",
                    }
                ],
            )
        else:
            tool_message = next(
                (message for message in reversed(messages) if message.type == "tool"),
                None,
            )
            content = f"工具返回：{tool_message.content if tool_message else '无工具结果'}"
            message = AIMessage(content=content)
        return ChatResult(generations=[ChatGeneration(message=message)])


def build_demo_agent() -> Any:
    """创建一个离线可运行的 Agent。

    ContextDemoModel 让示例无需真实模型也能运行。它会先请求工具调用，
    工具通过 ToolRuntime[Context] 读取 agent.invoke(..., context=...) 传入的上下文。
    """

    return create_agent(
        model=ContextDemoModel(),
        tools=[get_user_profile],
        context_schema=Context,
        system_prompt="你是一个演示 runtime context 的助手。",
    )


def main() -> None:
    context = Context(user_id="U001")
    agent = build_demo_agent()
    response = agent.invoke(
        {"messages": [{"role": "user", "content": "读取当前用户资料"}]},
        context=context,
    )
    print("Agent 回复：", response["messages"][-1].content)


if __name__ == "__main__":
    main()

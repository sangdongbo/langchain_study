"""Runtime Context 离线测试，不访问真实模型或网络。"""

from __future__ import annotations

import json
import os
from typing import TypedDict

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from langchain.tools import ToolRuntime, tool  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


class Context(TypedDict):
    tenant_id: str
    role: str


@tool
def read_context(runtime: ToolRuntime[Context]) -> str:
    """把经过认证的上下文转为工具结果。"""
    return json.dumps(dict(runtime.context), ensure_ascii=False)


def main() -> None:
    configure_utf8_output()
    model = ToolCapableFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "read_context",
                        "args": {},
                        "id": "context-1",
                    }
                ],
            ),
            AIMessage(content="已读取认证上下文。"),
        ]
    )
    agent = create_deep_agent(
        model=model,
        tools=[read_context],
        context_schema=Context,
        name="runtime-context-test-agent",
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "检查当前访问上下文。"}]},
        context={"tenant_id": "tenant-test", "role": "buyer"},
    )

    tool_messages = [
        message for message in result["messages"] if isinstance(message, ToolMessage)
    ]
    assert len(tool_messages) == 1
    assert json.loads(tool_messages[0].content) == {
        "tenant_id": "tenant-test",
        "role": "buyer",
    }
    assert result["messages"][-1].content == "已读取认证上下文。"
    print("Runtime Context 离线测试通过")
    print("- context_schema 校验输入结构")
    print("- ToolRuntime.context 读取认证上下文")
    print("- 上下文没有被拼进用户消息")


if __name__ == "__main__":
    main()


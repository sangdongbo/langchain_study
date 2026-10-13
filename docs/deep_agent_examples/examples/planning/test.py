"""TodoListMiddleware 离线测试，不访问真实模型或网络。"""

from __future__ import annotations

import os

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from langchain.agents.middleware import TodoListMiddleware  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


def main() -> None:
    configure_utf8_output()
    model = ToolCapableFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_todos",
                        "args": {
                            "todos": [
                                {"content": "检查库存", "status": "in_progress"},
                                {"content": "检查预算", "status": "pending"},
                            ]
                        },
                        "id": "todo-1",
                    }
                ],
            ),
            AIMessage(content="任务清单已建立，开始执行采购评审。"),
        ]
    )
    agent = create_deep_agent(
        model=model,
        middleware=[TodoListMiddleware()],
        name="planning-test-agent",
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "规划一个采购评审任务。"}]}
    )

    assert result["todos"] == [
        {"content": "检查库存", "status": "in_progress"},
        {"content": "检查预算", "status": "pending"},
    ]
    todo_messages = [
        message
        for message in result["messages"]
        if isinstance(message, ToolMessage) and message.name == "write_todos"
    ]
    assert len(todo_messages) == 1
    assert result["messages"][-1].content == "任务清单已建立，开始执行采购评审。"
    print("Todo 任务规划离线测试通过")
    print("- Middleware 注入 write_todos 工具")
    print("- write_todos 更新 State.todos")
    print("- 模型在工具结果后继续生成最终消息")


if __name__ == "__main__":
    main()


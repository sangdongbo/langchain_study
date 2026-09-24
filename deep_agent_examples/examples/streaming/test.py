"""Streaming 离线测试：验证 v2 事件和子图命名空间。"""

from __future__ import annotations

import os

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import SubAgent, create_deep_agent  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


def main() -> None:
    configure_utf8_output()
    parent_model = ToolCapableFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "task",
                        "args": {
                            "description": "检查库存",
                            "subagent_type": "stream-reviewer",
                        },
                        "id": "stream-task-1",
                    }
                ],
            ),
            AIMessage(content="父 Agent 已汇总库存结果。"),
        ]
    )
    child_model = ToolCapableFakeModel(responses=[AIMessage(content="库存证据：可用 1 台。")])
    reviewer: SubAgent = {
        "name": "stream-reviewer",
        "description": "返回确定性的库存证据。",
        "model": child_model,
        "system_prompt": "直接返回库存证据。",
    }
    agent = create_deep_agent(
        model=parent_model,
        subagents=[reviewer],
        name="streaming-test-agent",
    )
    events = list(
        agent.stream(
            {"messages": [{"role": "user", "content": "检查库存并汇总。"}]},
            version="v2",
            subgraphs=True,
            stream_mode=["updates", "messages"],
        )
    )

    event_types = {event["type"] for event in events}
    assert "updates" in event_types
    assert "messages" in event_types
    assert any(event.get("ns") for event in events), "nested subgraph namespace is missing"
    assert any(
        "父 Agent 已汇总库存结果。" in getattr(event["data"][0], "content", "")
        for event in events
        if event["type"] == "messages"
    )
    print("Streaming 离线测试通过")
    print("- v2 事件包含统一 type/ns/data 结构")
    print("- 同时收到 updates 和 messages 事件")
    print("- subgraphs=True 暴露嵌套子 Agent namespace")


if __name__ == "__main__":
    main()


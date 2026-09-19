"""生命周期离线测试，同时验证同步 invoke 和异步 ainvoke。

运行命令：
    uv run python examples/lifecycle/test.py

预期结果：
    输出“生命周期离线测试通过”，并确认 hook 顺序和模型工具循环一致。
"""

from __future__ import annotations

import asyncio
import os

# 使用 Fake Model 时关闭 LangSmith，保证同步和异步结果不受网络影响。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from deep_agent_examples.lifecycle import (  # noqa: E402
    LifecycleProbeMiddleware,
    LifecycleState,
)
from deep_agent_examples.tools import calculate_total  # noqa: E402
from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


# 一次“模型请求工具 -> 工具执行 -> 模型总结”应产生的完整 hook 顺序。
EXPECTED = [
    "01 agent.before_agent",
    "02 agent.before_model",
    "03 agent.after_model(tool_calls=1)",
    "04 agent.before_model",
    "05 agent.after_model(tool_calls=0)",
    "06 agent.after_agent",
]


def build_agent():
    # 两条脚本响应分别代表首次工具调用和工具执行后的最终回答。
    model = ToolCapableFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculate_total",
                        "args": {"unit_price": 68000, "quantity": 4},
                        "id": "calculate-total",
                    }
                ],
            ),
            AIMessage(content="total checked"),
        ]
    )
    return create_deep_agent(
        model=model,
        tools=[calculate_total],
        middleware=[LifecycleProbeMiddleware("agent")],
        state_schema=LifecycleState,
        name="lifecycle-test-agent",
    )


async def _run_async() -> dict:
    # 每次重新构建 Agent，避免同步调用消耗掉异步调用需要的脚本响应。
    return await build_agent().ainvoke(
        {"messages": [{"role": "user", "content": "Calculate the total."}]}
    )


def main() -> None:
    configure_utf8_output()
    sync_result = build_agent().invoke(
        {"messages": [{"role": "user", "content": "Calculate the total."}]}
    )
    async_result = asyncio.run(_run_async())

    # invoke 与 ainvoke 必须记录完全一致的生命周期事件和最终消息。
    assert sync_result["lifecycle_events"] == EXPECTED
    assert async_result["lifecycle_events"] == EXPECTED
    assert sync_result["messages"][-1].content == "total checked"
    assert async_result["messages"][-1].content == "total checked"

    print("生命周期离线测试通过")
    print("- 同步 invoke 的 hook 顺序正确")
    print("- 异步 ainvoke 的 hook 顺序正确")
    print("- model -> tool -> model 循环正确")


if __name__ == "__main__":
    main()

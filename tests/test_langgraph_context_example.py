from __future__ import annotations

from importlib import import_module


def test_context_example_tool_reads_runtime_context() -> None:
    module = import_module("langGraph.TestContext")
    agent = module.build_demo_agent()

    response = agent.invoke(
        {"messages": [{"role": "user", "content": "读取当前用户资料"}]},
        context=module.Context(user_id="U001"),
    )

    assert response["messages"][-1].content == "工具返回：当前用户 U001：张三，上海销售。"

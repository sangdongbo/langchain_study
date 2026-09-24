"""复杂采购任务的 Todo 规划真实示例。"""

from __future__ import annotations

from uuid import uuid4

from deepagents import create_deep_agent
from langchain.agents.middleware import TodoListMiddleware
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    tracing_enabled,
    tracing_project,
)
from deep_agent_examples.tools import (
    calculate_total,
    check_budget,
    check_inventory,
    check_supplier,
)


def main() -> None:
    thread_id = f"planning-{uuid4().hex[:8]}"
    config = invoke_config("planning", thread_id)
    agent = create_deep_agent(
        model=build_model(),
        tools=[calculate_total, check_budget, check_inventory, check_supplier],
        # TodoListMiddleware 显式添加 write_todos；deepagents 0.7.x 默认不添加。
        middleware=[TodoListMiddleware()],
        name="planning-agent",
        system_prompt=(
            "这是一个复杂采购评审。先用 write_todos 拆分任务，再按顺序调用证据工具；"
            "每完成一步就更新 todos，全部完成后再用中文总结。"
        ),
    )

    with tracing_context(
        enabled=tracing_enabled(),
        project_name=tracing_project(),
        tags=["deep-agent-example", "planning"],
        metadata=config["metadata"],
    ):
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，"
                            "供应商北辰智能硬件。请拆解并完成完整评审。"
                        ),
                    }
                ]
            },
            config=config,
        )

    print(result["messages"][-1].content)
    print("\ntodos:")
    for todo in result.get("todos", []):
        print(f"- [{todo['status']}] {todo['content']}")
    print(f"\nthread_id: {thread_id}")


if __name__ == "__main__":
    main()


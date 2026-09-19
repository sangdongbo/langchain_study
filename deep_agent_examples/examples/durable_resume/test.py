"""Checkpoint 恢复离线测试，不访问真实模型或网络。

运行命令：
    uv run python examples/durable_resume/test.py
"""

from __future__ import annotations

import os

# 测试不使用真实模型，也不发送 tracing。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


# 记录副作用工具的真实执行次数，证明中断前不会提前执行。
EXECUTIONS: list[tuple[str, float]] = []


@tool
def reserve_budget(department: str, amount: float) -> str:
    """记录模拟预算锁定，用于证明批准前工具不会执行。"""
    EXECUTIONS.append((department, amount))
    return "reserved"


def build_agent(model, checkpointer):
    # interrupt_on=True 让工具在执行前暂停；Checkpointer 保存恢复所需状态。
    return create_deep_agent(
        # model：中断前生成工具调用，恢复后生成最终回答。
        model=model,
        # tools：注册需要保护的副作用工具。
        tools=[reserve_budget],
        # interrupt_on=True：每次调用该工具都在执行前暂停，默认允许审核决定。
        interrupt_on={"reserve_budget": True},
        # checkpointer：保存暂停点；恢复还必须复用同一个 thread_id。
        checkpointer=checkpointer,
        # 测试 Graph 的名称。
        name="durable-resume-test-agent",
    )


def main() -> None:
    configure_utf8_output()
    EXECUTIONS.clear()
    checkpointer = InMemorySaver()
    config = {"configurable": {"thread_id": "durable-resume-test"}}

    # 第一个模型只产生副作用工具调用，Graph 应在工具真正执行前中断。
    first_model = ToolCapableFakeModel(
        responses=[
            AIMessage(
                # content 为空表示模型只请求执行工具，不直接回答用户。
                content="",
                tool_calls=[
                    {
                        # name 选择工具，args 是待审核参数，id 关联恢复后的 ToolMessage。
                        "name": "reserve_budget",
                        "args": {"department": "研发平台部", "amount": 272000},
                        "id": "reserve-1",
                    }
                ],
            )
        ]
    )
    interrupted = build_agent(first_model, checkpointer).invoke(
        {"messages": [{"role": "user", "content": "锁定预算"}]},
        config=config,
    )

    # 中断存在、执行记录为空且 Checkpoint 已落盘，三个条件缺一不可。
    assert interrupted.get("__interrupt__")
    assert EXECUTIONS == []
    assert list(checkpointer.list(config))

    # 使用新模型和新 Graph 对象，但复用 Checkpointer 与 thread_id 恢复现场。
    resumed_model = ToolCapableFakeModel(
        responses=[AIMessage(content="预算已经锁定")]
    )
    result = build_agent(resumed_model, checkpointer).invoke(
        # decisions 与待审核动作按顺序对应；approve 让原工具参数继续执行。
        Command(resume={"decisions": [{"type": "approve"}]}),
        # 相同 thread_id 使新 Graph 对象找到原 Checkpoint。
        config=config,
    )

    # approve 后工具只执行一次，并继续使用恢复阶段的新模型完成回答。
    assert EXECUTIONS == [("研发平台部", 272000.0)]
    assert result["messages"][-1].content == "预算已经锁定"
    # 不同 thread_id 不能读取当前会话的 Checkpoint。
    other_config = {"configurable": {"thread_id": "another-thread"}}
    assert checkpointer.get_tuple(other_config) is None

    print("Checkpoint 恢复离线测试通过")
    print("- 人工批准前副作用工具不会执行")
    print("- 新 Graph 对象可通过相同 Checkpointer 和 thread_id 恢复")
    print("- 不同 thread_id 的 Checkpoint 相互隔离")


if __name__ == "__main__":
    main()

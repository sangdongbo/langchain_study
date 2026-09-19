"""并行子 Agent 离线测试，不访问真实模型或网络。

运行命令：
    uv run python examples/parallel_review/test.py
"""

from __future__ import annotations

import os
from threading import Barrier

# 并行性由本地 Runnable 验证，不需要外部模型或 trace。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import CompiledSubAgent, create_deep_agent  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


# 三个名称必须与父模型生成的 subagent_type 完全一致。
REVIEWERS = ("finance-reviewer", "inventory-reviewer", "supplier-reviewer")


def _task_calls() -> AIMessage:
    """让同一轮模型响应生成三个 task 调用，ToolNode 才有并行机会。"""
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "args": {"description": f"Run {name}.", "subagent_type": name},
                "id": f"task-{name}",
            }
            for name in REVIEWERS
        ],
    )


def main() -> None:
    configure_utf8_output()
    # Barrier 要求三个子任务都进入才能继续；串行调度会在这里超时。
    barrier = Barrier(len(REVIEWERS), timeout=3)

    def reviewer(name: str):
        def run(state: dict) -> dict:  # noqa: ARG001
            # 串行执行时第一个任务会超时；三个任务并行进入才能一起越过屏障。
            barrier.wait()
            return {"messages": [AIMessage(content=f"{name}:ok")]}

        return run

    # RunnableLambda 让三个子 Agent 的工作确定、快速且无需真实模型。
    subagents: list[CompiledSubAgent] = [
        {
            "name": name,
            "description": f"Deterministic {name}.",
            "runnable": RunnableLambda(reviewer(name)),
        }
        for name in REVIEWERS
    ]
    # 第一条响应一次发出三个 task，第二条响应汇总三份 ToolMessage。
    model = ToolCapableFakeModel(
        responses=[_task_calls(), AIMessage(content="三项审查已合并")]
    )
    agent = create_deep_agent(
        model=model,
        subagents=subagents,
        name="parallel-review-test-agent",
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "并行执行三项审查"}]}
    )

    # 不依赖完成顺序，按集合检查三份结果是否全部返回。
    task_results = {
        message.content
        for message in result["messages"]
        if isinstance(message, ToolMessage) and message.name == "task"
    }
    assert task_results == {f"{name}:ok" for name in REVIEWERS}
    assert result["messages"][-1].content == "三项审查已合并"
    assert barrier.n_waiting == 0 and not barrier.broken

    print("并行子 Agent 离线测试通过")
    print("- 同一模型响应发出三个 task 调用")
    print("- 三个子 Agent 确实并发进入执行")
    print("- 父 Agent 收齐结果后统一汇总")


if __name__ == "__main__":
    main()

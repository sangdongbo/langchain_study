"""Checkpoint 中断与恢复的真实模型示例。

运行命令：
    uv run python examples/durable_resume/run.py --decision approve
    uv run python examples/durable_resume/run.py --decision reject

本例使用 InMemorySaver 展示恢复协议。它可以在同一进程内重新创建 Graph 后恢复，
但进程退出后数据会消失；生产环境应替换为数据库支持的持久化 Checkpointer。
"""

from __future__ import annotations

import argparse
import json
from uuid import uuid4

from deepagents import create_deep_agent
from langchain_core.tools import tool
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    tracing_enabled,
    tracing_project,
)


@tool
def reserve_budget(department: str, amount: float) -> str:
    """模拟锁定部门预算；真实系统中这是需要人工批准的外部副作用。"""
    return json.dumps(
        {"status": "reserved", "department": department, "amount": amount},
        ensure_ascii=False,
    )


def build_agent(model, checkpointer):
    """使用同一个 Checkpointer 创建可中断、可恢复的 Agent Graph。"""
    return create_deep_agent(
        # model：中断前规划工具调用，恢复后读取工具/拒绝结果并生成结论。
        model=model,
        # tools：向模型开放的工具；reserve_budget 是本例唯一副作用动作。
        tools=[reserve_budget],
        # interrupt_on：命中指定工具时先暂停，未经决定不会真正执行工具。
        interrupt_on={
            "reserve_budget": {
                # allowed_decisions：调用方恢复时允许提交的人工决定类型。
                "allowed_decisions": ["approve", "reject"],
                # description：展示给审核人的风险说明，不是模型系统提示词。
                "description": "预算锁定会产生外部副作用，请确认是否执行。",
            }
        },
        # checkpointer：保存暂停位置和 State；恢复还必须使用相同 thread_id。
        checkpointer=checkpointer,
        # Graph/Trace 中的稳定名称。
        name="durable-resume-agent",
        # system_prompt：告诉模型恢复后的业务处理规则，不负责强制中断。
        system_prompt=(
            "先计算采购申请中的总额，然后调用 reserve_budget 一次。"
            "工具恢复后，根据执行或拒绝结果给出中文结论。"
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="演示 Checkpoint 中断和恢复。")
    parser.add_argument("--decision", choices=["approve", "reject"], default="approve")
    parser.add_argument("--thread-id", default=f"durable-{uuid4().hex[:8]}")
    args = parser.parse_args()

    # 恢复依赖 Checkpointer 与 thread_id 的组合；两次 invoke 必须复用这两个值。
    model = build_model()
    checkpointer = InMemorySaver()
    config = invoke_config("durable-resume", args.thread_id)
    agent = build_agent(model, checkpointer)

    with tracing_context(
        # enabled：是否记录 LangSmith Trace，不影响 Checkpoint 的保存与恢复。
        enabled=tracing_enabled(),
        # project_name：Trace 在 LangSmith 中所属项目。
        project_name=tracing_project(),
        # tags/metadata：检索运行所用，不会进入模型对话。
        tags=["deep-agent-example", "durable-resume"],
        metadata=config["metadata"],
    ):
        # 第一次调用会在 reserve_budget 真正执行前暂停，并写入 Checkpoint。
        interrupted = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "研发平台部采购 4 台服务器，单价 68000 元，请锁定预算。",
                    }
                ]
            },
            config=config,
        )
        print(f"interrupted: {bool(interrupted.get('__interrupt__'))}")
        print(f"checkpoint_count: {len(list(checkpointer.list(config)))}")

        # 丢弃旧 Graph 并重新创建，证明恢复依赖 Checkpointer + thread_id，
        # 而不是依赖原来的 Python Graph 对象仍然存在。
        agent = build_agent(model, checkpointer)
        # Command(resume=...) 把人工决定送回暂停点：approve 执行原工具，
        # reject 则生成拒绝结果，副作用工具不会运行。
        decision = (
            {"type": "approve"}
            if args.decision == "approve"
            else {"type": "reject", "message": "预算需要重新核算"}
        )
        result = agent.invoke(
            # resume.decisions 按中断动作顺序提供决定；这里仅有一个动作。
            Command(resume={"decisions": [decision]}),
            # 复用原 config，尤其是相同 thread_id，才能定位暂停的 Checkpoint。
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"thread_id: {args.thread_id}")


if __name__ == "__main__":
    main()

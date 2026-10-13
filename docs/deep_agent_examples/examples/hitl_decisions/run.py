"""HITL approve、edit、reject 三种决策的真实模型示例。

运行命令：
    uv run python examples/hitl_decisions/run.py --decision approve
    uv run python examples/hitl_decisions/run.py --decision edit
    uv run python examples/hitl_decisions/run.py --decision reject
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
def publish_decision(title: str, decision: str, summary: str) -> str:
    """模拟发布采购决定；该副作用工具必须经过人工审核。"""
    return json.dumps(
        {"status": "published", "title": title, "decision": decision, "summary": summary},
        ensure_ascii=False,
    )


def build_agent(model, checkpointer):
    # interrupt_on 把副作用工具变成人工审核点，并限制允许的三种决定。
    return create_deep_agent(
        # model：生成待审核工具参数，并在恢复后解释最终结果。
        model=model,
        # tools：本例只开放发布动作，便于观察三种 HITL 决策。
        tools=[publish_decision],
        # interrupt_on：在工具真正执行前暂停 Graph 并返回 action_requests。
        interrupt_on={
            "publish_decision": {
                # allowed_decisions：审核端可提交 approve、edit 或 reject。
                "allowed_decisions": ["approve", "edit", "reject"],
                # description：展示给人工审核界面的风险说明。
                "description": "发布采购决定前，请审核标题、决定和摘要。",
            }
        },
        # checkpointer：持久化中断现场；恢复调用必须复用同一个 thread_id。
        checkpointer=checkpointer,
        # Graph/Trace 中的稳定名称。
        name="hitl-decisions-agent",
        # system_prompt：约束模型如何处理审核结果，不替代强制中断配置。
        system_prompt=(
            "根据用户请求调用 publish_decision 一次。人工可能批准、修改或拒绝；"
            "恢复后说明实际执行结果，拒绝时不要重试。"
        ),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="演示 HITL 三种审核决策。")
    parser.add_argument("--decision", choices=["approve", "edit", "reject"], default="edit")
    parser.add_argument("--thread-id", default=f"hitl-{uuid4().hex[:8]}")
    args = parser.parse_args()

    # Checkpointer 保存中断现场；恢复时必须继续使用相同的 thread_id。
    checkpointer = InMemorySaver()
    agent = build_agent(build_model(), checkpointer)
    config = invoke_config("hitl-decisions", args.thread_id)

    with tracing_context(
        # enabled：是否上传 Trace，关闭时 HITL 仍正常工作。
        enabled=tracing_enabled(),
        # project_name：Trace 在 LangSmith 中所属项目。
        project_name=tracing_project(),
        # tags/metadata：只用于检索本次审核类型和示例。
        tags=["deep-agent-example", "hitl-decisions", args.decision],
        metadata=config["metadata"],
    ):
        # 第一次 invoke 在 publish_decision 真正执行前暂停，并返回待审核参数。
        interrupted = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "发布服务器采购评审结果：当前建议直接通过。",
                    }
                ]
            },
            config=config,
        )
        request = interrupted["__interrupt__"][0].value["action_requests"][0]
        print(f"pending_action: {request}")

        # approve 使用模型原参数；edit 由人工替换参数；reject 完全不执行工具。
        if args.decision == "approve":
            decision = {"type": "approve"}
        elif args.decision == "edit":
            decision = {
                "type": "edit",
                "edited_action": {
                    "name": "publish_decision",
                    "args": {
                        "title": "服务器采购评审",
                        "decision": "conditional",
                        "summary": "补充库存方案后再执行采购。",
                    },
                },
            }
        else:
            decision = {"type": "reject", "message": "证据不足，暂不发布"}

        # Command 将人工决定送回原暂停点，而不是重新开始一轮模型调用。
        result = agent.invoke(
            # decisions 列表与待审核 action_requests 顺序一一对应。
            Command(resume={"decisions": [decision]}),
            # 复用原 config/thread_id，从原暂停点继续而不是新开一次执行。
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"thread_id: {args.thread_id}")


if __name__ == "__main__":
    main()

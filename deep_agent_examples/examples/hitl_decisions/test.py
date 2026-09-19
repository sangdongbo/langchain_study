"""HITL 三种决策离线测试，不访问真实模型或网络。

运行命令：
    uv run python examples/hitl_decisions/test.py
"""

from __future__ import annotations

import json
import os

# 三种审核分支都在内存中运行，不发送真实模型或 tracing 请求。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.types import Command  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


# 记录副作用工具实际收到的参数；reject 分支不应增加任何记录。
PUBLISHED: list[dict] = []


@tool
def publish_decision(title: str, decision: str, summary: str) -> str:
    """记录真正执行的发布参数，拒绝分支不应进入这里。"""
    record = {"title": title, "decision": decision, "summary": summary}
    PUBLISHED.append(record)
    return json.dumps(record, ensure_ascii=False)


# 原始参数来自模型 tool_call，编辑参数模拟人工审核后的替换值。
ORIGINAL_ARGS = {
    "title": "服务器采购评审",
    "decision": "approved",
    "summary": "预算和供应商已检查。",
}
EDITED_ARGS = {
    "title": "服务器采购评审",
    "decision": "conditional",
    "summary": "补充库存方案后再执行。",
}


def run_case(case: str, decision: dict) -> dict:
    # Fake Model 先请求发布工具，中断恢复后再给出最终回答。
    model = ToolCapableFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "publish_decision",
                        "args": ORIGINAL_ARGS,
                        "id": f"publish-{case}",
                    }
                ],
            ),
            AIMessage(content=f"{case} handled"),
        ]
    )
    checkpointer = InMemorySaver()
    agent = create_deep_agent(
        model=model,
        tools=[publish_decision],
        interrupt_on={
            "publish_decision": {
                "allowed_decisions": ["approve", "edit", "reject"],
                "description": "Review publication.",
            }
        },
        checkpointer=checkpointer,
        name=f"hitl-{case}-test-agent",
    )
    config = {"configurable": {"thread_id": f"hitl-{case}"}}

    # 第一次调用必须停在工具执行前，并暴露原参数及允许的决定类型。
    interrupted = agent.invoke(
        {"messages": [{"role": "user", "content": "发布评审"}]},
        config=config,
    )
    request = interrupted["__interrupt__"][0].value
    assert request["action_requests"][0]["args"] == ORIGINAL_ARGS
    assert request["review_configs"][0]["allowed_decisions"] == [
        "approve",
        "edit",
        "reject",
    ]
    # 使用相同 Graph、Checkpointer 和 thread_id 把人工决定送回暂停点。
    return agent.invoke(
        Command(resume={"decisions": [decision]}),
        config=config,
    )


def main() -> None:
    configure_utf8_output()
    PUBLISHED.clear()

    # approve：原参数原样执行。
    approved = run_case("approve", {"type": "approve"})
    assert PUBLISHED[-1] == ORIGINAL_ARGS
    assert approved["messages"][-1].content == "approve handled"

    # edit：只执行人工提供的新参数。
    edited = run_case(
        "edit",
        {
            "type": "edit",
            "edited_action": {"name": "publish_decision", "args": EDITED_ARGS},
        },
    )
    assert PUBLISHED[-1] == EDITED_ARGS
    assert edited["messages"][-1].content == "edit handled"

    # reject：工具完全不执行，框架返回带拒绝原因的 error ToolMessage。
    count_before_reject = len(PUBLISHED)
    rejected = run_case(
        "reject",
        {"type": "reject", "message": "证据不足"},
    )
    assert len(PUBLISHED) == count_before_reject
    rejection_message = next(
        message
        for message in rejected["messages"]
        if isinstance(message, ToolMessage) and message.tool_call_id == "publish-reject"
    )
    assert rejection_message.status == "error"
    assert "证据不足" in rejection_message.content

    print("HITL 多决策离线测试通过")
    print("- approve 使用原参数执行工具")
    print("- edit 使用人工修改后的参数执行工具")
    print("- reject 返回错误 ToolMessage，完全不执行工具")


if __name__ == "__main__":
    main()

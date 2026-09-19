"""声明式 SubAgent 离线测试，不需要模型 API Key。

运行命令：
    uv run python examples/declarative_subagent/test.py

预期结果：
    输出“声明式 SubAgent 离线测试通过”，并验证 isolated/fork 的消息隔离和 State 回传。
"""

from __future__ import annotations

import os
from typing import NotRequired

# 测试只使用脚本化模型，不上传 LangSmith trace。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import SubAgent, create_deep_agent  # noqa: E402
from deepagents.graph import DeepAgentState  # noqa: E402
from langchain.agents.middleware import AgentMiddleware  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


# 父子共享的公开 State 字段，用来观察子 Agent 的回写结果。
class SharedState(DeepAgentState):
    request_id: NotRequired[str]
    child_note: NotRequired[str]


class ChildNoteMiddleware(AgentMiddleware):
    state_schema = SharedState

    def after_agent(self, state, runtime):  # noqa: ARG002
        # 子 Agent 结束时记录它是否读到了父 State 的 request_id。
        return {"child_note": f"child-saw:{state.get('request_id')}"}


def _task_call(mode: str) -> AIMessage:
    # 父 Fake Model 首轮固定委派给 risk-reviewer。
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "args": {
                    "description": "Inspect delegated inventory risk only.",
                    "subagent_type": "risk-reviewer",
                },
                "id": f"task-{mode}",
            }
        ],
    )


def run_case(mode: str) -> tuple[dict, ToolCapableFakeModel]:
    # 子模型只返回报告；父模型先发 task，再基于 ToolMessage 汇总。
    child_model = ToolCapableFakeModel(
        responses=[AIMessage(content=f"{mode} child report")]
    )
    parent_model = ToolCapableFakeModel(
        responses=[_task_call(mode), AIMessage(content=f"{mode} parent report")]
    )
    child: SubAgent = {
        "name": "risk-reviewer",
        "description": "Deterministic child for propagation tests.",
        "model": child_model,
        "tools": [],
        "middleware": [ChildNoteMiddleware()],
        "mode": mode,
        "system_prompt": "Return the delegated result.",
    }
    parent = create_deep_agent(
        model=parent_model,
        subagents=[child],
        state_schema=SharedState,
        name=f"{mode}-parent-test",
    )
    result = parent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "PARENT_SECRET_CONTEXT: review this request.",
                }
            ],
            "request_id": f"request-{mode}",
        }
    )
    return result, child_model


def _message_texts(model: ToolCapableFakeModel) -> list[str]:
    return [
        str(message.content)
        for message in model.seen_messages[0]
        if isinstance(message, HumanMessage)
    ]


def main() -> None:
    configure_utf8_output()
    isolated, isolated_child = run_case("isolated")
    forked, forked_child = run_case("fork")

    isolated_text = "\n".join(_message_texts(isolated_child))
    forked_text = "\n".join(_message_texts(forked_child))

    # isolated 只能看到委派描述；fork 会继承有效父对话。
    assert "Inspect delegated inventory risk only." in isolated_text
    assert "PARENT_SECRET_CONTEXT" not in isolated_text
    assert "PARENT_SECRET_CONTEXT" in forked_text
    assert isolated["child_note"] == "child-saw:request-isolated"
    assert forked["child_note"] == "child-saw:request-fork"
    # 两种模式都会把子 Agent 最终回复包装为父侧 task ToolMessage。
    assert any(
        isinstance(message, ToolMessage) and message.content == "isolated child report"
        for message in isolated["messages"]
    )
    assert any(
        isinstance(message, ToolMessage) and message.content == "fork child report"
        for message in forked["messages"]
    )

    print("声明式 SubAgent 离线测试通过")
    print("- isolated 只接收委派任务，不接收父对话")
    print("- fork 会接收有效的父对话")
    print("- 两种模式都会把公开的自定义 State 返回给父 Agent")
    print("- 子 Agent 的最终 AIMessage 会成为父任务的 ToolMessage")


if __name__ == "__main__":
    main()

"""CompiledSubAgent 离线测试，不需要模型 API Key。

运行命令：
    uv run python examples/compiled_subagent/test.py

预期结果：
    输出“CompiledSubAgent 离线测试通过”，并验证结构化结果、消息结果和 State schema。
"""

from __future__ import annotations

import json
import os
from typing import Any, NotRequired

# 禁止测试产生外部 LangSmith 请求。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import CompiledSubAgent, create_deep_agent  # noqa: E402
from deepagents.graph import DeepAgentState  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402
from langgraph.graph import END, START, MessagesState, StateGraph  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


# 父 State 特意多一个 request_id，用来验证未声明字段不会泄漏给子图。
class ParentState(DeepAgentState):
    request_id: NotRequired[str]


class StructuredChildState(MessagesState):
    # CompiledSubAgent 会优先把 structured_response 作为 task 工具结果。
    structured_response: NotRequired[dict[str, Any]]


def _task_call(name: str, call_id: str) -> AIMessage:
    # 生成父模型调用内置 task 工具所需的标准 tool_call。
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "task",
                "args": {
                    "description": f"Run {name}.",
                    "subagent_type": name,
                },
                "id": call_id,
            }
        ],
    )


def main() -> None:
    configure_utf8_output()
    observed_child_keys: list[set[str]] = []

    def structured_node(state: StructuredChildState) -> dict:
        observed_child_keys.append(set(state))
        return {
            "messages": [AIMessage(content="human-readable fallback")],
            "structured_response": {"decision": "reject", "gap": 4000},
        }

    # 子图一同时返回文本和结构化结果，用来验证结构化结果优先。
    structured_builder = StateGraph(StructuredChildState)
    structured_builder.add_node("review", structured_node)
    structured_builder.add_edge(START, "review")
    structured_builder.add_edge("review", END)

    # 子图二没有 structured_response，应回退到最后一条非空 AIMessage。
    message_builder = StateGraph(MessagesState)
    message_builder.add_node(
        "review",
        lambda state: {"messages": [AIMessage(content="message-only result")]},
    )
    message_builder.add_edge(START, "review")
    message_builder.add_edge("review", END)

    # CompiledSubAgent 直接接收已经 compile 的 Runnable，不再重复创建 Agent。
    subagents: list[CompiledSubAgent] = [
        {
            "name": "structured-reviewer",
            "description": "Returns a structured finance decision.",
            "runnable": structured_builder.compile(),
        },
        {
            "name": "message-reviewer",
            "description": "Returns its last non-empty AIMessage.",
            "runnable": message_builder.compile(),
        },
    ]
    # 父模型依次委派两个子图，最后再合并两个 task 结果。
    parent_model = ToolCapableFakeModel(
        responses=[
            _task_call("structured-reviewer", "structured-task"),
            _task_call("message-reviewer", "message-task"),
            AIMessage(content="parent merged both results"),
        ]
    )
    parent = create_deep_agent(
        model=parent_model,
        subagents=subagents,
        state_schema=ParentState,
        name="compiled-parent-test",
    )
    result = parent.invoke(
        {
            "messages": [{"role": "user", "content": "Run both compiled graphs."}],
            "request_id": "parent-only-field",
        }
    )
    # 同时验证结果选择规则和 State schema 边界。
    task_messages = [
        message for message in result["messages"] if isinstance(message, ToolMessage)
    ]
    assert json.loads(task_messages[0].content) == {"decision": "reject", "gap": 4000}
    assert task_messages[1].content == "message-only result"
    assert "request_id" not in observed_child_keys[0]
    assert result["messages"][-1].content == "parent merged both results"

    # 错误案例：Runnable 没有返回 messages 时必须尽早给出诊断异常。
    broken_parent = create_deep_agent(
        model=ToolCapableFakeModel(
            responses=[_task_call("broken-reviewer", "broken-task")]
        ),
        subagents=[
            {
                "name": "broken-reviewer",
                "description": "Returns an invalid state without messages.",
                "runnable": RunnableLambda(lambda state: {"answer": "missing messages"}),
            }
        ],
        name="broken-compiled-parent-test",
    )
    try:
        broken_parent.invoke(
            {"messages": [{"role": "user", "content": "Run broken graph."}]}
        )
    except ValueError as error:
        assert "must return a state containing a 'messages' key" in str(error)
    else:
        raise AssertionError("CompiledSubAgent without messages must fail")

    print("CompiledSubAgent 离线测试通过")
    print("- structured_response 的优先级高于 AIMessage 文本")
    print("- 没有结构化输出时使用最后一条非空 AIMessage")
    print("- 编译后的子图不会继承未声明的父 State")
    print("- runnable 未返回 messages 时会给出明确错误")


if __name__ == "__main__":
    main()

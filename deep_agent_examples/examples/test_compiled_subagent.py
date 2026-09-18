"""Deterministic tests for CompiledSubAgent result and schema behavior."""

from __future__ import annotations

import json
import os
from typing import Any, NotRequired

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import CompiledSubAgent, create_deep_agent  # noqa: E402
from deepagents.graph import DeepAgentState  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.runnables import RunnableLambda  # noqa: E402
from langgraph.graph import END, START, MessagesState, StateGraph  # noqa: E402

from scripted_model import ToolCapableFakeModel  # noqa: E402


class ParentState(DeepAgentState):
    request_id: NotRequired[str]


class StructuredChildState(MessagesState):
    structured_response: NotRequired[dict[str, Any]]


def _task_call(name: str, call_id: str) -> AIMessage:
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
    observed_child_keys: list[set[str]] = []

    def structured_node(state: StructuredChildState) -> dict:
        observed_child_keys.append(set(state))
        return {
            "messages": [AIMessage(content="human-readable fallback")],
            "structured_response": {"decision": "reject", "gap": 4000},
        }

    structured_builder = StateGraph(StructuredChildState)
    structured_builder.add_node("review", structured_node)
    structured_builder.add_edge(START, "review")
    structured_builder.add_edge("review", END)

    message_builder = StateGraph(MessagesState)
    message_builder.add_node(
        "review",
        lambda state: {"messages": [AIMessage(content="message-only result")]},
    )
    message_builder.add_edge(START, "review")
    message_builder.add_edge("review", END)

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
    task_messages = [
        message for message in result["messages"] if isinstance(message, ToolMessage)
    ]
    assert json.loads(task_messages[0].content) == {"decision": "reject", "gap": 4000}
    assert task_messages[1].content == "message-only result"
    assert "request_id" not in observed_child_keys[0]
    assert result["messages"][-1].content == "parent merged both results"

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

    print("compiled subagent test passed")
    print("- structured_response takes precedence over AIMessage text")
    print("- last non-empty AIMessage is used when structured output is absent")
    print("- undeclared parent State is not inherited by the compiled graph")
    print("- a runnable without messages fails with a diagnostic error")


if __name__ == "__main__":
    main()

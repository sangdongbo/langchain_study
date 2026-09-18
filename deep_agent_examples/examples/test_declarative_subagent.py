"""Deterministic test for isolated and forked declarative SubAgents."""

from __future__ import annotations

import os
from typing import NotRequired

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import SubAgent, create_deep_agent  # noqa: E402
from deepagents.graph import DeepAgentState  # noqa: E402
from langchain.agents.middleware import AgentMiddleware  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

from scripted_model import ToolCapableFakeModel  # noqa: E402


class SharedState(DeepAgentState):
    request_id: NotRequired[str]
    child_note: NotRequired[str]


class ChildNoteMiddleware(AgentMiddleware):
    state_schema = SharedState

    def after_agent(self, state, runtime):  # noqa: ARG002
        return {"child_note": f"child-saw:{state.get('request_id')}"}


def _task_call(mode: str) -> AIMessage:
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
    isolated, isolated_child = run_case("isolated")
    forked, forked_child = run_case("fork")

    isolated_text = "\n".join(_message_texts(isolated_child))
    forked_text = "\n".join(_message_texts(forked_child))

    assert "Inspect delegated inventory risk only." in isolated_text
    assert "PARENT_SECRET_CONTEXT" not in isolated_text
    assert "PARENT_SECRET_CONTEXT" in forked_text
    assert isolated["child_note"] == "child-saw:request-isolated"
    assert forked["child_note"] == "child-saw:request-fork"
    assert any(
        isinstance(message, ToolMessage) and message.content == "isolated child report"
        for message in isolated["messages"]
    )
    assert any(
        isinstance(message, ToolMessage) and message.content == "fork child report"
        for message in forked["messages"]
    )

    print("declarative subagent test passed")
    print("- isolated receives the delegation, not the parent conversation")
    print("- fork receives the effective parent conversation")
    print("- public custom State returns to the parent in both modes")
    print("- child final AIMessage becomes the parent task ToolMessage")


if __name__ == "__main__":
    main()

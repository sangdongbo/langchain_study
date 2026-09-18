"""Deterministic executable test for State-backed Dynamic Skills.

This test uses a scripted fake chat model. It does not need an API key, call a
real model, or send traces to LangSmith.

Run from the deep_agent_examples directory:
    uv run python examples/test_dynamic_skills.py
"""

from __future__ import annotations

import os
from typing import Any

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import StateBackend  # noqa: E402
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from dynamic_skills import TrustedIdentity, skill_files_for  # noqa: E402
from scripted_model import ToolCapableFakeModel  # noqa: E402


PROCUREMENT_SKILL = """---
name: procurement-review
description: Review purchases using deterministic evidence
---

# Procurement Review

1. Read the request.
2. Check deterministic evidence.
3. Return a recommendation.
"""

SUPPLIER_SKILL = """---
name: supplier-research
description: Research supplier delivery risk
---

# Supplier Research

Check supplier delivery evidence.
"""


def _read_skill_call(call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[
            {
                "name": "read_file",
                "args": {
                    "file_path": "/skills/session/procurement-review/SKILL.md",
                    "limit": 1000,
                },
                "id": call_id,
            }
        ],
    )


def _system_text(messages: list[Any]) -> str:
    return "\n".join(
        str(message.content)
        for message in messages
        if isinstance(message, SystemMessage)
    )


def main() -> None:
    routed = skill_files_for(
        TrustedIdentity(tenant_id="tenant-a", role="risk-reviewer"),
        "supplier-risk",
    )
    assert set(routed) == {"/skills/session/supplier-research/SKILL.md"}
    try:
        skill_files_for(
            TrustedIdentity(tenant_id="tenant-a", role="buyer"),
            "supplier-risk",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("buyer must not receive supplier-research")

    model = ToolCapableFakeModel(
        responses=[
            _read_skill_call("read-skill-1"),
            AIMessage(content="first run complete"),
            _read_skill_call("read-skill-2"),
            AIMessage(content="second run complete"),
        ]
    )
    agent = create_deep_agent(
        model=model,
        backend=StateBackend(),
        skills=["/skills/session/"],
        checkpointer=InMemorySaver(),
        name="dynamic-skills-test-agent",
    )
    config = {"configurable": {"thread_id": "dynamic-skills-test"}}

    first = agent.invoke(
        {
            "messages": [{"role": "user", "content": "Review this purchase."}],
            "files": {
                "/skills/session/procurement-review/SKILL.md": {
                    "content": PROCUREMENT_SKILL,
                    "encoding": "utf-8",
                }
            },
        },
        config=config,
    )
    first_state = agent.get_state(config).values
    assert first["messages"][-1].content == "first run complete"
    assert [item["name"] for item in first_state["skills_metadata"]] == [
        "procurement-review"
    ]
    assert "procurement-review" in _system_text(model.seen_messages[0])
    assert "# Procurement Review" not in _system_text(model.seen_messages[0])
    assert any(
        isinstance(message, ToolMessage) and "# Procurement Review" in message.text
        for message in model.seen_messages[1]
    )

    second = agent.invoke(
        {
            "messages": [{"role": "user", "content": "Now research the supplier."}],
            "files": {
                "/skills/session/supplier-research/SKILL.md": {
                    "content": SUPPLIER_SKILL,
                    "encoding": "utf-8",
                }
            },
        },
        config=config,
    )
    second_state = agent.get_state(config).values
    assert second["messages"][-1].content == "second run complete"
    assert "/skills/session/supplier-research/SKILL.md" in second_state["files"]
    assert [item["name"] for item in second_state["skills_metadata"]] == [
        "procurement-review"
    ]
    assert all(
        "supplier-research" not in _system_text(messages)
        for messages in model.seen_messages[2:]
    )

    print("dynamic skills test passed")
    print("- trusted role/task routing allows and rejects the expected Skill bundles")
    print("- metadata is injected before the first model call")
    print("- full SKILL.md enters messages only after read_file")
    print("- same-thread metadata remains cached after adding another Skill file")


if __name__ == "__main__":
    main()

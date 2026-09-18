"""Deterministic sync/async test for the lifecycle probe Middleware.

Run from the deep_agent_examples directory:
    uv run python examples/test_lifecycle.py
"""

from __future__ import annotations

import asyncio
import os

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402

from deep_agent_examples.lifecycle import (  # noqa: E402
    LifecycleProbeMiddleware,
    LifecycleState,
)
from deep_agent_examples.tools import calculate_total  # noqa: E402
from scripted_model import ToolCapableFakeModel  # noqa: E402


EXPECTED = [
    "01 agent.before_agent",
    "02 agent.before_model",
    "03 agent.after_model(tool_calls=1)",
    "04 agent.before_model",
    "05 agent.after_model(tool_calls=0)",
    "06 agent.after_agent",
]


def build_agent():
    model = ToolCapableFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "calculate_total",
                        "args": {"unit_price": 68000, "quantity": 4},
                        "id": "calculate-total",
                    }
                ],
            ),
            AIMessage(content="total checked"),
        ]
    )
    return create_deep_agent(
        model=model,
        tools=[calculate_total],
        middleware=[LifecycleProbeMiddleware("agent")],
        state_schema=LifecycleState,
        name="lifecycle-test-agent",
    )


async def _run_async() -> dict:
    return await build_agent().ainvoke(
        {"messages": [{"role": "user", "content": "Calculate the total."}]}
    )


def main() -> None:
    sync_result = build_agent().invoke(
        {"messages": [{"role": "user", "content": "Calculate the total."}]}
    )
    async_result = asyncio.run(_run_async())

    assert sync_result["lifecycle_events"] == EXPECTED
    assert async_result["lifecycle_events"] == EXPECTED
    assert sync_result["messages"][-1].content == "total checked"
    assert async_result["messages"][-1].content == "total checked"

    print("lifecycle test passed")
    print("- sync invoke hook order verified")
    print("- async ainvoke hook order verified")
    print("- model -> tool -> model loop verified")


if __name__ == "__main__":
    main()

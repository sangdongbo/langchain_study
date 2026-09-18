"""Run an isolated or forked declarative SubAgent with LangSmith tracing.

Run from the deep_agent_examples directory:
    uv run python examples/declarative_subagent.py --mode isolated
    uv run python examples/declarative_subagent.py --mode fork
"""

from __future__ import annotations

import argparse
from uuid import uuid4

from deepagents import SubAgent, create_deep_agent
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    tracing_enabled,
    tracing_project,
)
from deep_agent_examples.tools import (
    calculate_total,
    check_budget,
    check_inventory,
    check_supplier,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a declarative SubAgent in isolated or fork mode."
    )
    parser.add_argument("--mode", choices=["isolated", "fork"], default="isolated")
    parser.add_argument(
        "--thread-id",
        default=f"declarative-subagent-{uuid4().hex[:8]}",
    )
    args = parser.parse_args()

    model = build_model()
    risk_reviewer: SubAgent = {
        "name": "risk-reviewer",
        "description": "Checks inventory, supplier, and delivery risk.",
        "model": model,
        "tools": [check_inventory, check_supplier],
        "mode": args.mode,
        "system_prompt": (
            "Use both tools and return only evidence, risks, and mitigations in Chinese."
        ),
    }
    agent = create_deep_agent(
        model=model,
        tools=[calculate_total, check_budget],
        subagents=[risk_reviewer],
        name=f"declarative-{args.mode}-parent",
        system_prompt=(
            "Check total and budget yourself. Delegate inventory and supplier risk "
            "exactly once to risk-reviewer, then merge the conclusions in Chinese."
        ),
    )
    config = invoke_config(f"declarative-subagent-{args.mode}", args.thread_id)
    config["metadata"].update(
        {
            "entrypoint": "examples/declarative_subagent.py",
            "subagent_kind": "declarative",
            "subagent_mode": args.mode,
        }
    )

    trace_on = tracing_enabled()
    with tracing_context(
        enabled=trace_on,
        project_name=tracing_project(),
        tags=["deep-agent-example", "subagent", "declarative", args.mode],
        metadata=config["metadata"],
    ):
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，"
                            "供应商北辰智能硬件。"
                        ),
                    }
                ]
            },
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"\nmode: {args.mode}")
    print(f"thread_id: {args.thread_id}")
    if trace_on:
        print(f"LangSmith project: {tracing_project()}")
    else:
        print("LangSmith tracing disabled; set LANGSMITH_TRACING=true to enable it.")


if __name__ == "__main__":
    main()

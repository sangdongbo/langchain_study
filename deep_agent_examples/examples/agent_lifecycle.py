"""Run ordinary or synchronous-subagent lifecycle examples with LangSmith tracing.

Run from the deep_agent_examples directory:
    uv run python examples/agent_lifecycle.py --kind agent
    uv run python examples/agent_lifecycle.py --kind subagent
"""

from __future__ import annotations

import argparse
from uuid import uuid4

from langsmith import tracing_context

from deep_agent_examples.config import invoke_config, tracing_enabled, tracing_project


PROMPTS = {
    "agent": "计算采购 4 台、单价 68000 元的总额。",
    "subagent": "让 lifecycle-reviewer 检查采购 4 台 AI 推理服务器的库存。",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an Agent lifecycle and print the recorded State events."
    )
    parser.add_argument("--kind", choices=sorted(PROMPTS), default="agent")
    parser.add_argument("--prompt", help="Override the default prompt.")
    parser.add_argument(
        "--thread-id",
        default=f"lifecycle-{uuid4().hex[:8]}",
    )
    args = parser.parse_args()

    from deep_agent_examples.graphs import (
        lifecycle_agent,
        subagent_lifecycle_agent,
    )

    graph = lifecycle_agent if args.kind == "agent" else subagent_lifecycle_agent
    config = invoke_config(f"{args.kind}-lifecycle-py", args.thread_id)
    config["metadata"]["entrypoint"] = "examples/agent_lifecycle.py"

    trace_on = tracing_enabled()
    with tracing_context(
        enabled=trace_on,
        project_name=tracing_project(),
        tags=["deep-agent-example", "lifecycle", args.kind, "python-file"],
        metadata=config["metadata"],
    ):
        result = graph.invoke(
            {
                "messages": [
                    {"role": "user", "content": args.prompt or PROMPTS[args.kind]}
                ]
            },
            config=config,
        )

    print(result["messages"][-1].content)
    fields = (
        ["lifecycle_events"]
        if args.kind == "agent"
        else ["parent_lifecycle_events", "child_lifecycle_events"]
    )
    for field in fields:
        print(f"\n{field}:")
        for event in result.get(field, []):
            print(f"- {event}")
    if trace_on:
        print(f"\nLangSmith project: {tracing_project()}")
    else:
        print("\nLangSmith tracing disabled; set LANGSMITH_TRACING=true to enable it.")


if __name__ == "__main__":
    main()

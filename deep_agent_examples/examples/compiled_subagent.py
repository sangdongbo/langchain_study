"""Run the precompiled finance SubAgent with LangSmith tracing."""

from __future__ import annotations

import argparse
from uuid import uuid4

from langsmith import tracing_context

from deep_agent_examples.config import invoke_config, tracing_enabled, tracing_project


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a CompiledSubAgent example.")
    parser.add_argument(
        "--thread-id",
        default=f"compiled-subagent-{uuid4().hex[:8]}",
    )
    args = parser.parse_args()

    from deep_agent_examples.graphs import compiled_subagent_agent

    config = invoke_config("compiled-subagent-py", args.thread_id)
    config["metadata"].update(
        {
            "entrypoint": "examples/compiled_subagent.py",
            "subagent_kind": "compiled",
        }
    )
    trace_on = tracing_enabled()
    with tracing_context(
        enabled=trace_on,
        project_name=tracing_project(),
        tags=["deep-agent-example", "subagent", "compiled"],
        metadata=config["metadata"],
    ):
        result = compiled_subagent_agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，"
                            "供应商北辰智能硬件，并让财务图独立复核。"
                        ),
                    }
                ]
            },
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"\nthread_id: {args.thread_id}")
    if trace_on:
        print(f"LangSmith project: {tracing_project()}")
    else:
        print("LangSmith tracing disabled; set LANGSMITH_TRACING=true to enable it.")


if __name__ == "__main__":
    main()

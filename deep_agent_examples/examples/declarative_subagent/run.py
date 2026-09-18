"""声明式 SubAgent 真实演示：比较 isolated 和 fork 两种模式。

运行条件：
    在 deep_agent_examples 目录配置模型 API Key。

运行命令：
    uv run python examples/declarative_subagent/run.py --mode isolated
    uv run python examples/declarative_subagent/run.py --mode fork

预期结果：
    输出子 Agent 审核结果、当前 mode、thread_id，以及 LangSmith tracing 是否启用。

离线测试：
    uv run python examples/declarative_subagent/test.py
    测试通过时输出“声明式 SubAgent 离线测试通过”。
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
            "entrypoint": "examples/declarative_subagent/run.py",
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

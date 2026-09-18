"""AsyncSubAgent 真实演示：通过 Agent Protocol 启动并查询后台任务。

运行条件：
    1. 在 deep_agent_examples 目录配置模型 API Key。
    2. 先运行：uv run langgraph dev --host 127.0.0.1 --port 2024

运行命令：
    uv run python examples/async_subagent/run.py
    uv run python examples/async_subagent/run.py --check-after 5

预期结果：
    输出 task_id、remote run_id、cached status 和 parent thread_id。
    使用 --check-after 时，还会输出 checked status 和远程任务结果。

离线测试：
    uv run python examples/async_subagent/test.py
    测试通过时输出“AsyncSubAgent 离线测试通过”。
"""

from __future__ import annotations

import argparse
import asyncio
import os
from uuid import uuid4

from deepagents import AsyncSubAgent, create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    load_environment,
    tracing_enabled,
    tracing_project,
)
from deep_agent_examples.tools import calculate_total, check_budget


async def run(check_after: float | None, thread_id: str) -> None:
    load_environment()
    spec: AsyncSubAgent = {
        "name": "remote-procurement-researcher",
        "description": "Researches supplier and inventory risk in the background.",
        "graph_id": "remote_research_agent",
        "url": os.getenv("AGENT_SERVER_URL") or "http://127.0.0.1:2024",
    }
    if token := os.getenv("AGENT_SERVER_TOKEN"):
        spec["headers"] = {"Authorization": f"Bearer {token}"}

    agent = create_deep_agent(
        model=build_model(),
        tools=[calculate_total, check_budget],
        subagents=[spec],
        checkpointer=InMemorySaver(),
        name="async-subagent-parent-example",
        system_prompt=(
            "When asked to start background research, call start_async_task exactly "
            "once and return its exact task_id. Never poll unless explicitly asked."
        ),
    )
    config = invoke_config("async-subagent-py", thread_id)
    config["metadata"].update(
        {
            "entrypoint": "examples/async_subagent/run.py",
            "subagent_kind": "async",
            "remote_graph_id": spec["graph_id"],
            "agent_server_url": spec["url"],
        }
    )

    trace_on = tracing_enabled()
    with tracing_context(
        enabled=trace_on,
        project_name=tracing_project(),
        tags=["deep-agent-example", "subagent", "async"],
        metadata=config["metadata"],
    ):
        result = await agent.ainvoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "请在后台调查北辰智能硬件和 AI 推理服务器库存，"
                            "启动后只返回 task_id。"
                        ),
                    }
                ]
            },
            config=config,
        )
        tasks = result.get("async_tasks") or {}
        if not tasks:
            raise RuntimeError("The model did not call start_async_task; inspect the trace.")
        task_id = next(iter(tasks))

        print(result["messages"][-1].content)
        print(f"\ntask_id: {task_id}")
        print(f"remote run_id: {tasks[task_id]['run_id']}")
        print(f"cached status: {tasks[task_id]['status']}")

        if check_after is not None:
            await asyncio.sleep(check_after)
            checked = await agent.ainvoke(
                {
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"Call check_async_task exactly once for task_id "
                                f"{task_id}, then report the exact status and result."
                            ),
                        }
                    ]
                },
                config=config,
            )
            current = checked["async_tasks"][task_id]
            print(f"\nchecked status: {current['status']}")
            print(checked["messages"][-1].content)

    print(f"\nparent thread_id: {thread_id}")
    if trace_on:
        print(f"LangSmith project: {tracing_project()}")
    else:
        print("LangSmith tracing disabled; set LANGSMITH_TRACING=true to enable it.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run an AsyncSubAgent example.")
    parser.add_argument(
        "--check-after",
        type=float,
        help="Wait this many seconds and perform one check; omission means start only.",
    )
    parser.add_argument(
        "--thread-id",
        default=f"async-subagent-{uuid4().hex[:8]}",
    )
    args = parser.parse_args()
    if args.check_after is not None and args.check_after < 0:
        parser.error("--check-after must be non-negative")
    asyncio.run(run(args.check_after, args.thread_id))


if __name__ == "__main__":
    main()

"""AsyncSubAgent 离线测试，使用 Fake Agent Protocol，不访问网络。

运行命令：
    uv run python examples/async_subagent/test.py

预期结果：
    输出“AsyncSubAgent 离线测试通过”，并确认后台任务可以启动、查询、更新和取消。
"""

from __future__ import annotations

import asyncio
import os
from typing import Any
from unittest.mock import patch

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import AsyncSubAgent, create_deep_agent  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


class FakeThreads:
    async def create(self) -> dict[str, str]:
        return {"thread_id": "remote-thread-1"}

    async def get(self, thread_id: str) -> dict[str, Any]:
        assert thread_id == "remote-thread-1"
        return {"values": {"messages": [{"content": "remote research result"}]}}


class FakeRuns:
    def __init__(self) -> None:
        self.create_calls: list[dict[str, Any]] = []
        self.cancel_calls: list[tuple[str, str]] = []

    async def create(self, **kwargs: Any) -> dict[str, str]:
        self.create_calls.append(kwargs)
        return {"run_id": f"remote-run-{len(self.create_calls)}"}

    async def get(self, thread_id: str, run_id: str) -> dict[str, str]:
        assert thread_id == "remote-thread-1"
        assert run_id == "remote-run-1"
        return {"status": "success"}

    async def cancel(self, thread_id: str, run_id: str) -> None:
        self.cancel_calls.append((thread_id, run_id))


class FakeAgentProtocolClient:
    def __init__(self) -> None:
        self.threads = FakeThreads()
        self.runs = FakeRuns()


def _tool_call(name: str, args: dict[str, Any], call_id: str) -> AIMessage:
    return AIMessage(
        content="",
        tool_calls=[{"name": name, "args": args, "id": call_id}],
    )


async def run_test() -> None:
    model = ToolCapableFakeModel(
        responses=[
            _tool_call(
                "start_async_task",
                {
                    "description": "Research supplier risk.",
                    "subagent_type": "remote-researcher",
                },
                "start-task",
            ),
            AIMessage(content="started"),
            _tool_call(
                "check_async_task",
                {"task_id": "remote-thread-1"},
                "check-task",
            ),
            AIMessage(content="checked"),
            _tool_call(
                "update_async_task",
                {
                    "task_id": "remote-thread-1",
                    "message": "Also check delivery history.",
                },
                "update-task",
            ),
            AIMessage(content="updated"),
            _tool_call(
                "cancel_async_task",
                {"task_id": "remote-thread-1"},
                "cancel-task",
            ),
            AIMessage(content="cancelled"),
        ]
    )
    spec: AsyncSubAgent = {
        "name": "remote-researcher",
        "description": "Fake remote researcher.",
        "graph_id": "remote_graph",
        "url": "http://fake-agent-server",
    }
    client = FakeAgentProtocolClient()
    config = {"configurable": {"thread_id": "parent-thread-1"}}

    with patch(
        "deepagents.middleware.async_subagents.get_client",
        return_value=client,
    ):
        agent = create_deep_agent(
            model=model,
            subagents=[spec],
            checkpointer=InMemorySaver(),
            name="async-parent-test",
        )
        started = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "Start research."}]},
            config=config,
        )
        task = started["async_tasks"]["remote-thread-1"]
        assert task["task_id"] == task["thread_id"] == "remote-thread-1"
        assert task["run_id"] == "remote-run-1"
        assert task["status"] == "running"

        checked = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "Check it."}]},
            config=config,
        )
        assert checked["async_tasks"]["remote-thread-1"]["status"] == "success"

        updated = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "Update it."}]},
            config=config,
        )
        updated_task = updated["async_tasks"]["remote-thread-1"]
        assert updated_task["thread_id"] == "remote-thread-1"
        assert updated_task["run_id"] == "remote-run-2"
        assert updated_task["status"] == "running"
        assert client.runs.create_calls[1]["multitask_strategy"] == "interrupt"

        cancelled = await agent.ainvoke(
            {"messages": [{"role": "user", "content": "Cancel it."}]},
            config=config,
        )
        assert cancelled["async_tasks"]["remote-thread-1"]["status"] == "cancelled"
        assert client.runs.cancel_calls == [
            ("remote-thread-1", "remote-run-2")
        ]

    print("AsyncSubAgent 离线测试通过")
    print("- 启动任务会创建远程 thread/run 并保存跟踪信息")
    print("- 查询任务会刷新缓存状态并读取远程结果")
    print("- 更新任务会保留 task_id/thread_id 并替换 run_id")
    print("- 取消任务会终止当前远程 run 并记录最终状态")


def main() -> None:
    configure_utf8_output()
    asyncio.run(run_test())


if __name__ == "__main__":
    main()

"""CompositeBackend 离线测试，不访问真实模型或网络。"""

from __future__ import annotations

import os

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


NAMESPACE = ("tenant-test", "files")


def build_agent(store: InMemoryStore, model: ToolCapableFakeModel):
    backend = CompositeBackend(
        default=StateBackend(),
        routes={
            "/memories/": StoreBackend(
                namespace=lambda _runtime: NAMESPACE,
                store=store,
            )
        },
    )
    return create_deep_agent(
        model=model,
        backend=backend,
        checkpointer=InMemorySaver(),
        name="composite-backend-test-agent",
    )


def main() -> None:
    configure_utf8_output()
    store = InMemoryStore()
    model = ToolCapableFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/work/evidence.md",
                            "content": "本 thread 的证据",
                        },
                        "id": "write-work",
                    },
                    {
                        "name": "write_file",
                        "args": {
                            "file_path": "/memories/decision.md",
                            "content": "跨 thread 的采购决策",
                        },
                        "id": "write-memory",
                    },
                ],
            ),
            AIMessage(content="两个文件已按路由保存。"),
        ]
    )
    result = build_agent(store, model).invoke(
        {"messages": [{"role": "user", "content": "保存证据和决策。"}]},
        config={"configurable": {"thread_id": "composite-thread"}},
    )

    state_files = result.get("files", {})
    assert state_files["/work/evidence.md"]["content"] == "本 thread 的证据"
    assert "/memories/decision.md" not in state_files
    stored = store.get(NAMESPACE, "/decision.md")
    assert stored is not None
    assert stored.value["content"] == "跨 thread 的采购决策"
    assert result["messages"][-1].content == "两个文件已按路由保存。"
    print("CompositeBackend 离线测试通过")
    print("- /work/ 路由到 StateBackend")
    print("- /memories/ 路由到 StoreBackend")
    print("- 临时文件与跨 thread 文件彼此隔离")


if __name__ == "__main__":
    main()


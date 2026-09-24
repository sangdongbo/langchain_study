"""CompositeBackend 真实示例。"""

from __future__ import annotations

from uuid import uuid4

from deepagents import create_deep_agent
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    tracing_enabled,
    tracing_project,
)


TENANT_NAMESPACE = ("tenant-a", "files")


def build_agent(store: InMemoryStore):
    backend = CompositeBackend(
        # 默认路由：临时工作文件保存在当前 Graph State。
        default=StateBackend(),
        routes={
            # /memories/ 下的文件改走跨 thread Store。
            "/memories/": StoreBackend(
                namespace=lambda _runtime: TENANT_NAMESPACE,
                store=store,
            )
        },
    )
    return create_deep_agent(
        model=build_model(),
        backend=backend,
        checkpointer=InMemorySaver(),
        name="composite-backend-agent",
        system_prompt=(
            "把本次证据写入 /work/evidence.md，把需要跨会话保留的采购决策写入 "
            "/memories/decision.md，最后告诉用户两个路径。"
        ),
    )


def main() -> None:
    store = InMemoryStore()
    agent = build_agent(store)
    thread_id = f"composite-{uuid4().hex[:8]}"
    config = invoke_config("composite-backend", thread_id)
    with tracing_context(
        enabled=tracing_enabled(),
        project_name=tracing_project(),
        tags=["deep-agent-example", "composite-backend"],
        metadata=config["metadata"],
    ):
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "记录本次采购评审证据，并保存最终决策。",
                    }
                ]
            },
            config=config,
        )

    print(result["messages"][-1].content)
    print("state files:", sorted(result.get("files", {})))
    print("store files:", ["/memories/decision.md"] if store.get(TENANT_NAMESPACE, "/decision.md") else [])
    print(f"thread_id: {thread_id}")


if __name__ == "__main__":
    main()


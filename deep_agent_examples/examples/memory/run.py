"""跨 thread Memory 真实示例。

运行命令：
    uv run python examples/memory/run.py

这个示例使用 StoreBackend 保存 AGENTS.md，再由 memory 参数加载到模型上下文。
"""

from __future__ import annotations

from uuid import uuid4

from deepagents import create_deep_agent
from deepagents.backends import StoreBackend
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    tracing_enabled,
    tracing_project,
)


TENANT_NAMESPACE = ("tenant-a", "memory")
MEMORY_PATH = "/AGENTS.md"
MEMORY_CONTENT = """# 采购助手长期规则

- 默认使用中文回答。
- 采购评审必须区分工具证据和模型推测。
- 金额计算必须调用确定性工具，不要心算。
"""


def build_memory_agent(store: InMemoryStore):
    """创建从租户 Store 加载 AGENTS.md 的 Agent。"""
    backend = StoreBackend(
        # namespace：按租户隔离跨 thread 文件，不能直接信任用户文本。
        namespace=lambda _runtime: TENANT_NAMESPACE,
        # store：示例使用内存 Store；生产环境替换成持久化 BaseStore。
        store=store,
    )
    return create_deep_agent(
        model=build_model(),
        # memory：列出每次 Agent 启动都要读取的 AGENTS.md 文件。
        memory=[MEMORY_PATH],
        # backend：MemoryMiddleware 通过它查找 memory 文件。
        backend=backend,
        # checkpointer：只负责 thread 内 State；Store 负责跨 thread 文件。
        checkpointer=InMemorySaver(),
        name="memory-agent",
        system_prompt="回答时说明使用了哪些记忆规则，但不要把记忆当成权限配置。",
    )


def main() -> None:
    store = InMemoryStore()
    store.put(
        TENANT_NAMESPACE,
        MEMORY_PATH,
        {"content": MEMORY_CONTENT, "encoding": "utf-8"},
    )
    agent = build_memory_agent(store)
    thread_id = f"memory-{uuid4().hex[:8]}"
    config = invoke_config("memory", thread_id)
    config["metadata"]["memory_namespace"] = "/".join(TENANT_NAMESPACE)

    with tracing_context(
        enabled=tracing_enabled(),
        project_name=tracing_project(),
        tags=["deep-agent-example", "memory"],
        metadata=config["metadata"],
    ):
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "请说明本次采购评审应该遵守哪些长期规则。",
                    }
                ]
            },
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"tenant: {'/'.join(TENANT_NAMESPACE)}")
    print(f"thread_id: {thread_id}")
    print(f"memory_file: {MEMORY_PATH}")


if __name__ == "__main__":
    main()


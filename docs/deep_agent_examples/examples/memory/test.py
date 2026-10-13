"""Memory 与 StoreBackend 离线测试。"""

from __future__ import annotations

import os

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import StoreBackend  # noqa: E402
from langchain_core.messages import AIMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402
from langgraph.store.memory import InMemoryStore  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


NAMESPACE = ("tenant-test", "memory")
MEMORY_PATH = "/AGENTS.md"
MEMORY_TEXT = "租户规则：采购结论必须使用中文，并标明证据来源。"


def build_agent(store: InMemoryStore, model: ToolCapableFakeModel):
    return create_deep_agent(
        model=model,
        backend=StoreBackend(
            namespace=lambda _runtime: NAMESPACE,
            store=store,
        ),
        memory=[MEMORY_PATH],
        checkpointer=InMemorySaver(),
        name="memory-test-agent",
    )


def main() -> None:
    configure_utf8_output()
    store = InMemoryStore()
    store.put(NAMESPACE, MEMORY_PATH, {"content": MEMORY_TEXT, "encoding": "utf-8"})

    # 两个 Agent 分别使用不同 thread，底层 Store 仍然是同一个租户空间。
    first_model = ToolCapableFakeModel(responses=[AIMessage(content="first")])
    second_model = ToolCapableFakeModel(responses=[AIMessage(content="second")])
    first = build_agent(store, first_model)
    second = build_agent(store, second_model)
    first.invoke(
        {"messages": [{"role": "user", "content": "读取我的记忆。"}]},
        config={"configurable": {"thread_id": "memory-thread-a"}},
    )
    second.invoke(
        {"messages": [{"role": "user", "content": "读取我的记忆。"}]},
        config={"configurable": {"thread_id": "memory-thread-b"}},
    )

    for model in (first_model, second_model):
        system_messages = [
            message
            for message in model.seen_messages[0]
            if getattr(message, "type", "") == "system"
        ]
        assert system_messages, "MemoryMiddleware should inject a system message"
        content = system_messages[0].content
        if isinstance(content, list):
            content = "".join(
                block.get("text", "") for block in content if isinstance(block, dict)
            )
        assert MEMORY_TEXT in content

    saved = store.get(NAMESPACE, MEMORY_PATH)
    assert saved is not None and saved.value["content"] == MEMORY_TEXT
    print("Memory 离线测试通过")
    print("- AGENTS.md 已注入模型 system prompt")
    print("- 不同 thread 共享同一租户 Store")
    print("- Memory 与 thread checkpoint 分层正确")


if __name__ == "__main__":
    main()

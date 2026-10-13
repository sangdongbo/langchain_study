"""Streaming 真实示例：同时观察父 Agent 和同步子 Agent。"""

from __future__ import annotations

from uuid import uuid4

from deepagents import SubAgent, create_deep_agent
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    tracing_enabled,
    tracing_project,
)
from deep_agent_examples.tools import check_inventory


def _text(content) -> str:
    """把字符串或内容块转换为适合终端打印的文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(
            block.get("text", "") for block in content if isinstance(block, dict)
        )
    return str(content)


def main() -> None:
    model = build_model()
    reviewer: SubAgent = {
        "name": "stream-inventory-reviewer",
        "description": "检查 AI 推理服务器库存并返回证据。",
        "model": model,
        "tools": [check_inventory],
        "system_prompt": "调用库存工具后，用中文返回简短证据。",
    }
    agent = create_deep_agent(
        model=model,
        subagents=[reviewer],
        name="streaming-agent",
        system_prompt="把库存检查委派给 stream-inventory-reviewer，再汇总结果。",
    )
    thread_id = f"stream-{uuid4().hex[:8]}"
    config = invoke_config("streaming", thread_id)

    with tracing_context(
        enabled=tracing_enabled(),
        project_name=tracing_project(),
        tags=["deep-agent-example", "streaming"],
        metadata=config["metadata"],
    ):
        for event in agent.stream(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": "检查 4 台 AI 推理服务器的库存并给出结论。",
                    }
                ]
            },
            config=config,
            # v2 让不同事件类型有统一的 type/ns/data 外壳。
            version="v2",
            # 打开后会把同步子 Agent 的嵌套事件也发到当前迭代器。
            subgraphs=True,
            stream_mode=["updates", "messages"],
        ):
            event_type = event["type"]
            namespace = "/".join(event.get("ns", ())) or "parent"
            if event_type == "updates":
                print(f"[updates][{namespace}] {list(event['data'])}")
            elif event_type == "messages":
                message, metadata = event["data"]
                text = _text(getattr(message, "content", ""))
                if text:
                    node = metadata.get("langgraph_node", "model")
                    print(f"[messages][{namespace}][{node}] {text}")

    print(f"thread_id: {thread_id}")


if __name__ == "__main__":
    main()


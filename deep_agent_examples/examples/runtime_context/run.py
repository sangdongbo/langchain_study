"""Runtime Context 真实示例。"""

from __future__ import annotations

import json
from typing import TypedDict
from uuid import uuid4

from deepagents import create_deep_agent
from langchain.tools import ToolRuntime, tool
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    tracing_enabled,
    tracing_project,
)


class RequestContext(TypedDict):
    """认证层传给本次 Graph 调用的只读上下文。"""

    tenant_id: str
    role: str
    feature_flags: dict[str, bool]


@tool
def get_authorized_scope(runtime: ToolRuntime[RequestContext]) -> str:
    """返回当前认证身份可以访问的采购数据范围。"""
    context = runtime.context
    role = context["role"]
    scope = "采购评审和供应商风险" if role == "risk-reviewer" else "采购评审"
    return json.dumps(
        {
            "tenant_id": context["tenant_id"],
            "role": role,
            "scope": scope,
            "supplier_research_enabled": context["feature_flags"].get(
                "supplier_research", False
            ),
        },
        ensure_ascii=False,
    )


def main() -> None:
    thread_id = f"context-{uuid4().hex[:8]}"
    config = invoke_config("runtime-context", thread_id)
    agent = create_deep_agent(
        model=build_model(),
        tools=[get_authorized_scope],
        # context_schema：声明每次 invoke 可以传入的运行时上下文结构。
        context_schema=RequestContext,
        name="runtime-context-agent",
        system_prompt="需要确认权限范围时调用 get_authorized_scope，再用中文回答。",
    )
    context: RequestContext = {
        "tenant_id": "tenant-a",
        "role": "risk-reviewer",
        "feature_flags": {"supplier_research": True},
    }

    with tracing_context(
        enabled=tracing_enabled(),
        project_name=tracing_project(),
        tags=["deep-agent-example", "runtime-context"],
        # 不把完整 context 写入 Trace metadata，避免把内部身份数据泄露到日志。
        metadata=config["metadata"],
    ):
        result = agent.invoke(
            {
                "messages": [
                    {"role": "user", "content": "我现在可以访问哪些采购数据？"}
                ]
            },
            config=config,
            context=context,
        )

    print(result["messages"][-1].content)
    print(f"thread_id: {thread_id}")
    print("context: tenant-a / risk-reviewer")


if __name__ == "__main__":
    main()


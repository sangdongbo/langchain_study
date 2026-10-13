"""生命周期真实演示：观察普通 Agent 或同步子 Agent 的执行顺序。

运行条件：
    在 deep_agent_examples 目录配置模型 API Key。

运行命令：
    uv run python examples/lifecycle/run.py --kind agent
    uv run python examples/lifecycle/run.py --kind subagent

预期结果：
    输出模型结果和按顺序记录的 lifecycle_events；启用 tracing 时还会输出 LangSmith 项目。

离线测试：
    uv run python examples/lifecycle/test.py
    测试通过时输出“生命周期离线测试通过”。
"""

from __future__ import annotations

import argparse
from uuid import uuid4

from langsmith import tracing_context

from deep_agent_examples.config import invoke_config, tracing_enabled, tracing_project


PROMPTS = {
    "agent": "计算采购 4 台、单价 68000 元的总额。",
    "subagent": "让 lifecycle-reviewer 检查采购 4 台 AI 推理服务器的库存。",
}


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run an Agent lifecycle and print the recorded State events."
    )
    parser.add_argument("--kind", choices=sorted(PROMPTS), default="agent")
    parser.add_argument("--prompt", help="Override the default prompt.")
    parser.add_argument(
        "--thread-id",
        default=f"lifecycle-{uuid4().hex[:8]}",
    )
    args = parser.parse_args()

    # graphs 模块分别导出普通 Agent 和带父/子探针的同步 SubAgent Graph。
    from deep_agent_examples.graphs import (
        lifecycle_agent,
        subagent_lifecycle_agent,
    )

    # 两类 Graph 的事件字段不同，但都使用同一个 thread 配置和输入方式。
    graph = lifecycle_agent if args.kind == "agent" else subagent_lifecycle_agent
    config = invoke_config(f"{args.kind}-lifecycle-py", args.thread_id)
    config["metadata"]["entrypoint"] = "examples/lifecycle/run.py"

    trace_on = tracing_enabled()
    with tracing_context(
        # enabled：是否上传 Trace；生命周期事件本身始终写入 Graph State。
        enabled=trace_on,
        # project_name：Trace 在 LangSmith 中归属的项目。
        project_name=tracing_project(),
        # tags：用于按 Graph 类型筛选，不会进入模型上下文。
        tags=["deep-agent-example", "lifecycle", args.kind, "python-file"],
        # metadata：附加到 Trace 的运行信息，不是 Agent State。
        metadata=config["metadata"],
    ):
        # LifecycleProbeMiddleware 会把每个 hook 按实际发生顺序追加到 State。
        result = graph.invoke(
            {
                "messages": [
                    {"role": "user", "content": args.prompt or PROMPTS[args.kind]}
                ]
            },
            # config 携带 thread_id 和追踪信息；messages 才是模型看到的输入。
            config=config,
        )

    print(result["messages"][-1].content)
    # 普通 Agent 只有一条事件流；SubAgent 示例分别打印父、子两条事件流。
    fields = (
        ["lifecycle_events"]
        if args.kind == "agent"
        else ["parent_lifecycle_events", "child_lifecycle_events"]
    )
    for field in fields:
        print(f"\n{field}:")
        for event in result.get(field, []):
            print(f"- {event}")
    if trace_on:
        print(f"\nLangSmith project: {tracing_project()}")
    else:
        print("\nLangSmith tracing disabled; set LANGSMITH_TRACING=true to enable it.")


if __name__ == "__main__":
    main()

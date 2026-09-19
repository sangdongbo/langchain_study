"""CompiledSubAgent 真实演示：调用预编译的财务审核子 Agent。

运行条件：
    在 deep_agent_examples 目录配置模型 API Key。

运行命令：
    uv run python examples/compiled_subagent/run.py

预期结果：
    输出财务审核结果、thread_id，以及 LangSmith tracing 是否启用。

离线测试：
    uv run python examples/compiled_subagent/test.py
    测试通过时输出“CompiledSubAgent 离线测试通过”。
"""

from __future__ import annotations

import argparse
from uuid import uuid4

from langsmith import tracing_context

from deep_agent_examples.config import invoke_config, tracing_enabled, tracing_project


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a CompiledSubAgent example.")
    parser.add_argument(
        "--thread-id",
        default=f"compiled-subagent-{uuid4().hex[:8]}",
    )
    args = parser.parse_args()

    # graphs 模块会按环境配置创建真实模型，延迟导入可先完成命令行参数解析。
    from deep_agent_examples.graphs import compiled_subagent_agent

    # CompiledSubAgent 已在 graphs.py 中把可复用的财务 Graph 注册给父 Agent。
    # 这里仅为本次调用补充 thread、标签和可观测性元数据。
    config = invoke_config("compiled-subagent-py", args.thread_id)
    config["metadata"].update(
        {
            "entrypoint": "examples/compiled_subagent/run.py",
            "subagent_kind": "compiled",
        }
    )
    trace_on = tracing_enabled()
    with tracing_context(
        # enabled：只控制是否上传 LangSmith Trace，不影响 Graph 执行。
        enabled=trace_on,
        # project_name：Trace 在 LangSmith 中归属的项目。
        project_name=tracing_project(),
        # tags：便于筛选本示例，不会进入模型上下文。
        tags=["deep-agent-example", "subagent", "compiled"],
        # metadata：随 Trace 保存的结构化信息，不是 Graph 输入 State。
        metadata=config["metadata"],
    ):
        # 父 Agent 检查库存/供应商，再通过 task 工具调用预编译财务 Graph。
        result = compiled_subagent_agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，"
                            "供应商北辰智能硬件，并让财务图独立复核。"
                        ),
                    }
                ]
            },
            # config 提供 thread_id、run_name 和追踪信息，与 messages 输入分开。
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"\nthread_id: {args.thread_id}")
    if trace_on:
        print(f"LangSmith project: {tracing_project()}")
    else:
        print("LangSmith tracing disabled; set LANGSMITH_TRACING=true to enable it.")


if __name__ == "__main__":
    main()

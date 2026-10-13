"""声明式 SubAgent 真实演示：比较 isolated 和 fork 两种模式。

运行条件：
    在 deep_agent_examples 目录配置模型 API Key。

运行命令：
    uv run python examples/declarative_subagent/run.py --mode isolated
    uv run python examples/declarative_subagent/run.py --mode fork

预期结果：
    输出子 Agent 审核结果、当前 mode、thread_id，以及 LangSmith tracing 是否启用。

离线测试：
    uv run python examples/declarative_subagent/test.py
    测试通过时输出“声明式 SubAgent 离线测试通过”。
"""

from __future__ import annotations

import argparse
from uuid import uuid4

from deepagents import SubAgent, create_deep_agent
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    tracing_enabled,
    tracing_project,
)
from deep_agent_examples.tools import (
    calculate_total,
    check_budget,
    check_inventory,
    check_supplier,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a declarative SubAgent in isolated or fork mode."
    )
    parser.add_argument("--mode", choices=["isolated", "fork"], default="isolated")
    parser.add_argument(
        "--thread-id",
        default=f"declarative-subagent-{uuid4().hex[:8]}",
    )
    args = parser.parse_args()

    model = build_model()
    # 子 Agent 只拥有库存和供应商工具；mode 决定它是否继承父对话：
    # isolated 只接收委派描述，fork 会看到父 Agent 当前的有效消息。
    risk_reviewer: SubAgent = {
        # name：父模型调用 task 时使用的子 Agent 路由名，父级内必须唯一。
        "name": "risk-reviewer",
        # description：给父模型看的能力说明，决定何时适合委派。
        "description": "Checks inventory, supplier, and delivery risk.",
        # model：子 Agent 自己的推理模型，可以和父 Agent 不同。
        "model": model,
        # tools：子 Agent 的工具白名单，不会继承父 Agent 的工具。
        "tools": [check_inventory, check_supplier],
        # mode：isolated 仅接收任务描述；fork 还会复制父对话上下文。
        "mode": args.mode,
        # system_prompt：仅约束子 Agent 的角色、工具使用和输出。
        "system_prompt": (
            "Use both tools and return only evidence, risks, and mitigations in Chinese."
        ),
    }
    # 父 Agent 保留金额和预算职责，并通过 task 工具把风险审查委派给子 Agent。
    agent = create_deep_agent(
        # 父 Agent 用这个模型规划、委派并汇总答案。
        model=model,
        # 仅父 Agent 可直接调用的金额和预算工具。
        tools=[calculate_total, check_budget],
        # 注册后框架会向父模型暴露 task 委派工具。
        subagents=[risk_reviewer],
        # 父 Graph 在 Studio/Trace 中的名称。
        name=f"declarative-{args.mode}-parent",
        # 父 Agent 的职责边界；不会覆盖子 Agent 的 system_prompt。
        system_prompt=(
            "Check total and budget yourself. Delegate inventory and supplier risk "
            "exactly once to risk-reviewer, then merge the conclusions in Chinese."
        ),
    )
    # 把运行模式写入 metadata，便于在 LangSmith 中比较 isolated/fork 轨迹。
    config = invoke_config(f"declarative-subagent-{args.mode}", args.thread_id)
    config["metadata"].update(
        {
            "entrypoint": "examples/declarative_subagent/run.py",
            "subagent_kind": "declarative",
            "subagent_mode": args.mode,
        }
    )

    trace_on = tracing_enabled()
    with tracing_context(
        # 是否向 LangSmith 上传本次调用链；关闭时 Agent 仍正常执行。
        enabled=trace_on,
        # Trace 归属的 LangSmith 项目名。
        project_name=tracing_project(),
        # 可检索标签，不会进入模型上下文。
        tags=["deep-agent-example", "subagent", "declarative", args.mode],
        # 结构化追踪元数据，用于比较两种 mode。
        metadata=config["metadata"],
    ):
        # 同一采购输入分别以两种 mode 运行，才能直观看到上下文传播差异。
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，"
                            "供应商北辰智能硬件。"
                        ),
                    }
                ]
            },
            # config 中的 thread_id 负责区分会话 State，metadata 只用于追踪。
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"\nmode: {args.mode}")
    print(f"thread_id: {args.thread_id}")
    if trace_on:
        print(f"LangSmith project: {tracing_project()}")
    else:
        print("LangSmith tracing disabled; set LANGSMITH_TRACING=true to enable it.")


if __name__ == "__main__":
    main()

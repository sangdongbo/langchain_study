"""三个采购审查子 Agent 并行委派的真实模型示例。

运行命令：
    uv run python examples/parallel_review/run.py
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
    parser = argparse.ArgumentParser(description="并行执行三个采购审查子任务。")
    parser.add_argument("--thread-id", default=f"parallel-{uuid4().hex[:8]}")
    args = parser.parse_args()

    model = build_model()
    # 三个子 Agent 各自只拥有完成本职审查所需的最小工具集合。
    reviewers: list[SubAgent] = [
        {
            # name：父模型 task 调用的目标名；同一列表中必须唯一。
            "name": "finance-reviewer",
            # description：父模型根据它判断应该委派哪类任务。
            "description": "计算采购总额并检查部门预算。",
            # model：这个子 Agent 自己的推理模型。
            "model": model,
            # tools：只授权完成财务检查所需的两个工具。
            "tools": [calculate_total, check_budget],
            # system_prompt：该子 Agent 的独立工作要求。
            "system_prompt": "使用两个工具，返回简短的中文财务证据。",
        },
        {
            # 三个字典字段含义相同：路由名、路由说明、子模型和工具白名单。
            "name": "inventory-reviewer",
            "description": "检查申请物品的库存是否充足。",
            "model": model,
            "tools": [check_inventory],
            "system_prompt": "查询库存并返回简短的中文库存证据。",
        },
        {
            "name": "supplier-reviewer",
            "description": "检查供应商评分、风险和延期交付记录。",
            "model": model,
            "tools": [check_supplier],
            "system_prompt": "查询供应商并返回简短的中文风险证据。",
        },
    ]
    # 父 Agent 不直接持有业务工具；它必须在同一轮生成三个 task 调用，
    # ToolNode 才能并行调度三项互不依赖的审查。
    agent = create_deep_agent(
        # 父模型负责一次生成三个 task 调用并最终汇总。
        model=model,
        # 注册三个声明式子 Agent；父 Agent 本身没有业务 tools。
        subagents=reviewers,
        # 父 Graph 在 Trace 中的稳定名称。
        name="parallel-review-agent",
        # 并行是否发生取决于模型是否在同一响应中生成多个 task 调用。
        system_prompt=(
            "你是采购评审负责人。第一轮必须在同一个模型响应中分别调用三次 task，"
            "并行委派 finance-reviewer、inventory-reviewer、supplier-reviewer。"
            "收到三份证据后再统一给出中文结论，不要重复执行子任务。"
        ),
    )
    config = invoke_config("parallel-review", args.thread_id)

    with tracing_context(
        # enabled 只开关追踪，不影响并行调度逻辑。
        enabled=tracing_enabled(),
        # project_name 决定 Trace 在 LangSmith 中归属哪个项目。
        project_name=tracing_project(),
        # tags/metadata 只用于检索和诊断，不会传给子 Agent。
        tags=["deep-agent-example", "parallel-review"],
        metadata=config["metadata"],
    ):
        # 父 Agent 收齐三个 ToolMessage 后再进入下一轮模型调用统一汇总。
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
            # config 中的 thread_id 标识本次会话；并行子任务共享父运行上下文。
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"thread_id: {args.thread_id}")


if __name__ == "__main__":
    main()

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
            "name": "finance-reviewer",
            "description": "计算采购总额并检查部门预算。",
            "model": model,
            "tools": [calculate_total, check_budget],
            "system_prompt": "使用两个工具，返回简短的中文财务证据。",
        },
        {
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
        model=model,
        subagents=reviewers,
        name="parallel-review-agent",
        system_prompt=(
            "你是采购评审负责人。第一轮必须在同一个模型响应中分别调用三次 task，"
            "并行委派 finance-reviewer、inventory-reviewer、supplier-reviewer。"
            "收到三份证据后再统一给出中文结论，不要重复执行子任务。"
        ),
    )
    config = invoke_config("parallel-review", args.thread_id)

    with tracing_context(
        enabled=tracing_enabled(),
        project_name=tracing_project(),
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
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"thread_id: {args.thread_id}")


if __name__ == "__main__":
    main()

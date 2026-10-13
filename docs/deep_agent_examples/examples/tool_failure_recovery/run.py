"""工具失败、自动重试和耗尽降级的真实模型示例。

运行命令：
    uv run python examples/tool_failure_recovery/run.py --failures 2
"""

from __future__ import annotations

import argparse
import json

from deepagents import create_deep_agent
from langchain.agents.middleware import ToolRetryMiddleware
from langchain_core.tools import tool
from langsmith import tracing_context

from deep_agent_examples.config import build_model, tracing_enabled, tracing_project


# 用计数器模拟同一外部接口连续失败若干次后恢复。
ATTEMPTS = 0
FAILURES_BEFORE_SUCCESS = 2


@tool
def query_delivery_risk(supplier: str) -> str:
    """模拟不稳定的只读供应商接口，在指定次数后恢复。"""
    global ATTEMPTS
    ATTEMPTS += 1
    if ATTEMPTS <= FAILURES_BEFORE_SUCCESS:
        raise TimeoutError(f"供应商接口第 {ATTEMPTS} 次调用超时")
    return json.dumps(
        {"supplier": supplier, "risk": "medium", "attempts": ATTEMPTS},
        ensure_ascii=False,
    )


def main() -> None:
    global ATTEMPTS, FAILURES_BEFORE_SUCCESS
    parser = argparse.ArgumentParser(description="演示工具自动重试和失败降级。")
    parser.add_argument("--failures", type=int, choices=range(0, 6), default=2)
    args = parser.parse_args()
    ATTEMPTS = 0
    FAILURES_BEFORE_SUCCESS = args.failures

    # max_retries=2 表示首次调用失败后最多再试两次，总调用次数最多为 3。
    # 只重试 TimeoutError；耗尽后 on_failure 把异常转换为可供模型处理的消息。
    retry = ToolRetryMiddleware(
        # max_retries：首次失败后最多额外执行两次，不含第一次调用。
        max_retries=2,
        # tools：只对列表中的工具应用本重试策略，其他工具不受影响。
        tools=[query_delivery_risk],
        # retry_on：只有这些异常类型会重试，业务校验错误会直接返回。
        retry_on=(TimeoutError,),
        # initial_delay：第一次重试前等待 0.2 秒。
        initial_delay=0.2,
        # backoff_factor：后续等待时间按 2 倍指数增长。
        backoff_factor=2.0,
        # max_delay：单次退避最多等待 1 秒。
        max_delay=1.0,
        # jitter=False：不增加随机抖动，方便示例复现固定时序。
        jitter=False,
        # on_failure：重试耗尽后把异常变成 ToolMessage 内容，交给模型降级回答。
        on_failure=lambda error: f"供应商服务暂不可用：{error}",
    )
    # Middleware 包裹工具执行，模型只发起一次工具调用，不负责手工重试。
    agent = create_deep_agent(
        # model：只看到最终成功结果或 on_failure 生成的错误消息。
        model=build_model(),
        # tools：向模型注册可调用的供应商查询工具。
        tools=[query_delivery_risk],
        # middleware：在工具节点外包一层自动重试逻辑。
        middleware=[retry],
        # Graph/Trace 中的名称。
        name="tool-failure-recovery-agent",
        # 约束模型只发起一次工具调用，重试由 Middleware 内部完成。
        system_prompt=(
            "调用 query_delivery_risk 一次检查北辰智能硬件。"
            "工具内部可能自动重试；根据最终成功数据或错误消息给出中文结论。"
        ),
    )

    with tracing_context(
        # enabled：是否上传 LangSmith Trace，不影响重试行为。
        enabled=tracing_enabled(),
        # project_name：Trace 所属项目。
        project_name=tracing_project(),
        # tags/metadata：用于筛选重试示例及其模拟失败次数。
        tags=["deep-agent-example", "tool-retry"],
        metadata={"failures_before_success": args.failures},
    ):
        # failures 为 0~2 时最终成功；大于 2 时重试耗尽并走降级消息。
        result = agent.invoke(
            {"messages": [{"role": "user", "content": "检查北辰智能硬件交付风险"}]}
        )

    print(result["messages"][-1].content)
    print(f"tool_attempts: {ATTEMPTS}")


if __name__ == "__main__":
    main()

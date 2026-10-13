"""ToolRetryMiddleware 离线测试，不访问真实模型或网络。

运行命令：
    uv run python examples/tool_failure_recovery/test.py
"""

from __future__ import annotations

import os

# 通过确定性异常验证 Middleware，不访问真实供应商接口。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from langchain.agents.middleware import ToolRetryMiddleware  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


# 分别统计“最终恢复”和“始终失败”两个工具的实际调用次数。
ATTEMPTS = {"flaky": 0, "down": 0}


@tool
def flaky_inventory(item: str) -> str:
    """前两次失败、第三次成功的模拟只读接口。"""
    ATTEMPTS["flaky"] += 1
    if ATTEMPTS["flaky"] < 3:
        raise TimeoutError("temporary timeout")
    return f"{item}:available"


@tool
def unavailable_supplier(supplier: str) -> str:
    """始终不可用，用于验证重试耗尽后的错误消息。"""
    ATTEMPTS["down"] += 1
    raise ConnectionError(f"{supplier}:offline")


def _tool_call(name: str, args: dict, call_id: str) -> AIMessage:
    # 构造 Fake Model 请求工具执行的标准消息。
    return AIMessage(
        # 空 content 表示本轮只请求工具执行。
        content="",
        # name/args 指定工具和参数，id 用于关联返回的 ToolMessage。
        tool_calls=[{"name": name, "args": args, "id": call_id}],
    )


def main() -> None:
    configure_utf8_output()
    ATTEMPTS.update(flaky=0, down=0)

    # 成功场景：首次调用加两次重试，第三次返回有效库存。
    success_model = ToolCapableFakeModel(
        responses=[
            _tool_call("flaky_inventory", {"item": "AI 推理服务器"}, "flaky-1"),
            AIMessage(content="库存查询最终成功"),
        ]
    )
    success_agent = create_deep_agent(
        # model：预制工具调用和成功后的最终回复。
        model=success_model,
        # tools：向模型注册 flaky_inventory。
        tools=[flaky_inventory],
        # middleware：只在工具执行阶段处理异常和重试。
        middleware=[
            ToolRetryMiddleware(
                # 首次失败后最多额外重试两次，总调用上限为三次。
                max_retries=2,
                # 只有 TimeoutError 才会触发重试。
                retry_on=(TimeoutError,),
                # 测试把延迟、退避和随机抖动全部关闭，保证立即且可重复。
                initial_delay=0,
                backoff_factor=0,
                jitter=False,
            )
        ],
        name="retry-success-test-agent",
    )
    success = success_agent.invoke(
        {"messages": [{"role": "user", "content": "查询库存"}]}
    )
    success_tool_message = next(
        message for message in success["messages"] if isinstance(message, ToolMessage)
    )
    assert ATTEMPTS["flaky"] == 3
    assert success_tool_message.content == "AI 推理服务器:available"
    assert success_tool_message.status == "success"

    # 降级场景：首次调用加一次重试仍失败，on_failure 生成 error ToolMessage。
    failure_model = ToolCapableFakeModel(
        responses=[
            _tool_call(
                "unavailable_supplier",
                {"supplier": "北辰智能硬件"},
                "supplier-1",
            ),
            AIMessage(content="供应商服务不可用，转人工核实"),
        ]
    )
    failure_agent = create_deep_agent(
        # model：读取重试耗尽后的 error ToolMessage 并输出降级结论。
        model=failure_model,
        # tools：注册始终失败的供应商查询工具。
        tools=[unavailable_supplier],
        # middleware：对 ConnectionError 重试一次，再执行 on_failure。
        middleware=[
            ToolRetryMiddleware(
                # 首次失败后仅额外调用一次，因此实际总调用次数为两次。
                max_retries=1,
                # 仅连接错误参与本策略。
                retry_on=(ConnectionError,),
                initial_delay=0,
                backoff_factor=0,
                jitter=False,
                # 重试耗尽时把异常转成错误工具消息，而不是抛出终止 Graph。
                on_failure=lambda error: f"已降级：{error}",
            )
        ],
        name="retry-failure-test-agent",
    )
    failure = failure_agent.invoke(
        {"messages": [{"role": "user", "content": "查询供应商"}]}
    )
    failure_tool_message = next(
        message for message in failure["messages"] if isinstance(message, ToolMessage)
    )
    assert ATTEMPTS["down"] == 2
    assert failure_tool_message.status == "error"
    assert "已降级" in failure_tool_message.content
    # 模型收到降级消息后仍能继续输出人工核实建议，而不是让 Graph 崩溃。
    assert failure["messages"][-1].content == "供应商服务不可用，转人工核实"

    print("工具失败恢复离线测试通过")
    print("- 临时超时在第三次调用时恢复")
    print("- 重试耗尽后返回 error ToolMessage")
    print("- 模型可以根据降级消息继续给出结论")


if __name__ == "__main__":
    main()

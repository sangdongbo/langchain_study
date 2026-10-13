"""通过本地异步生成器验证流式拼接和完成后的输出。"""

# 本地异步生成器替代网络流，测试不用等待真实模型逐字生成。
import asyncio

from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel

# 与 run.py 共用 Agent 定义，仅将模型替换为 FunctionModel。
from run import PROMPT, build_agent

# 禁止真实模型请求；CHUNKS 固定预期片段，便于检查追加逻辑是否重复文字。
models.ALLOW_MODEL_REQUESTS = False
CHUNKS = ["核对需求。", "检查预算。", "评估供应商。", "确认审批权限。"]


async def stream(messages, info):
    # yield 模拟提供方逐次交付文字；块大小只为测试设定，不代表真实 token 边界。
    for chunk in CHUNKS:
        yield chunk


async def check() -> None:
    # stream_function 指定异步流式响应，框架仍负责处理流结果与累计用量。
    async with build_agent(FunctionModel(stream_function=stream)).run_stream(PROMPT) as result:
        # 收集新增片段而不是累计快照；最终拼接应与框架完整输出一致。
        received = [chunk async for chunk in result.stream_text(delta=True, debounce_by=None)]
        output = await result.get_output()
        assert "".join(received) == output == "".join(CHUNKS)
        assert len(received) > 1
        # requests 记录框架请求次数，离线模型也会计数；它不表示真实网络请求。
        assert result.usage.requests == 1
        assert result.is_complete
        assert result.all_messages()
    print("06 PASS：异步流、增量拼接、最终输出")


# 测试脚本在终端创建自己的事件循环。
if __name__ == "__main__":
    asyncio.run(check())

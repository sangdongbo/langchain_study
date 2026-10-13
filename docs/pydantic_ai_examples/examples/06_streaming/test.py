"""通过本地异步生成器验证流式拼接和完成后的输出。"""

import asyncio

from pydantic_ai import models
from pydantic_ai.models.function import FunctionModel

from run import PROMPT, build_agent

models.ALLOW_MODEL_REQUESTS = False
CHUNKS = ["核对需求。", "检查预算。", "评估供应商。", "确认审批权限。"]


async def stream(messages, info):
    for chunk in CHUNKS:
        yield chunk


async def check() -> None:
    async with build_agent(FunctionModel(stream_function=stream)).run_stream(PROMPT) as result:
        received = [chunk async for chunk in result.stream_text(delta=True, debounce_by=None)]
        output = await result.get_output()
        assert "".join(received) == output == "".join(CHUNKS)
        assert len(received) > 1
        assert result.usage.requests == 1
        assert result.is_complete
        assert result.all_messages()
    print("06 PASS：异步流、增量拼接、最终输出")


if __name__ == "__main__":
    asyncio.run(check())

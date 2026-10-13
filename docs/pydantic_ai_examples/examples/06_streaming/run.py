"""06：异步消费文字增量，最后读取完整结果。"""

import asyncio

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from pydantic_examples.config import build_model

PROMPT = "请用四条简短建议说明如何评审一项服务器采购。"


def build_agent(model: Model) -> Agent[None, str]:
    return Agent(model, instructions="你是采购教学助手，用简洁中文回答。")


async def main() -> None:
    agent = build_agent(build_model())
    async with agent.run_stream(PROMPT, usage_limits=UsageLimits(request_limit=3)) as result:
        async for delta in result.stream_text(delta=True, debounce_by=None):
            print(delta, end="", flush=True)
        output = await result.get_output()
        print("\n完整结果字符数：", len(output))
        print("usage:", result.usage)


if __name__ == "__main__":
    asyncio.run(main())

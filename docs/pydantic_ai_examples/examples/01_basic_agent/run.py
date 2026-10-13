"""01：一个 Agent 的同步和异步入口。"""

import argparse
import asyncio

from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from pydantic_examples.config import build_model

PROMPT = "请用三句话解释：Agent 和普通聊天模型的区别是什么？"


def build_agent(model: Model) -> Agent[None, str]:
    return Agent(model, instructions="你是 Python 教学助手。用简洁中文回答。")


async def run_async(agent: Agent[None, str], prompt: str):
    return await agent.run(prompt, usage_limits=UsageLimits(request_limit=3))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--async", dest="use_async", action="store_true")
    parser.add_argument("--prompt", default=PROMPT)
    args = parser.parse_args()
    agent = build_agent(build_model())
    result = (
        asyncio.run(run_async(agent, args.prompt))
        if args.use_async
        else agent.run_sync(args.prompt, usage_limits=UsageLimits(request_limit=3))
    )
    print(result.output)
    print("usage:", result.usage)


if __name__ == "__main__":
    main()

"""不读取 .env、不访问真实模型的同步/异步检查。"""

import asyncio

from pydantic_ai import models
from pydantic_ai.models.test import TestModel

from run import build_agent, run_async

models.ALLOW_MODEL_REQUESTS = False


def main() -> None:
    agent = build_agent(TestModel(custom_output_text="Agent 可以调用工具。"))
    sync = agent.run_sync("解释 Agent")
    asynchronous = asyncio.run(run_async(agent, "解释 Agent"))
    assert sync.output == asynchronous.output == "Agent 可以调用工具。"
    assert sync.usage.requests == asynchronous.usage.requests == 1
    assert sync.new_messages()
    print("01 PASS：同步、异步和 usage")


if __name__ == "__main__":
    main()

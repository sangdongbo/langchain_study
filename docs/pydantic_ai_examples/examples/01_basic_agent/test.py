"""不读取 .env、不访问真实模型的同步/异步检查。"""

import asyncio

# TestModel 是官方离线模型，返回指定文字，但仍经过真实 Agent 的执行流程。
from pydantic_ai import models
from pydantic_ai.models.test import TestModel

# 直接运行 test.py 时，Python 可导入同目录 run.py；其 main 不会自动执行。
from run import build_agent, run_async

# 即使以后误接入真实供应商模型，也禁止测试发出模型网络请求。
models.ALLOW_MODEL_REQUESTS = False


def main() -> None:
    # 固定输出排除模型随机性，重点验证同步与异步入口得到同一种运行结果。
    agent = build_agent(TestModel(custom_output_text="Agent 可以调用工具。"))
    sync = agent.run_sync("解释 Agent")
    asynchronous = asyncio.run(run_async(agent, "解释 Agent"))
    # 离线模型也会累计框架请求计数；这里的 requests=1 不表示发生了网络请求。
    assert sync.output == asynchronous.output == "Agent 可以调用工具。"
    assert sync.usage.requests == asynchronous.usage.requests == 1
    assert sync.new_messages()
    print("01 PASS：同步、异步和 usage")


# 可单独演示，也可由 scripts_smoke.py 在独立进程中启动。
if __name__ == "__main__":
    main()

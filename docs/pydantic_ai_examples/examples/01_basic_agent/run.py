"""01：一个 Agent 的同步和异步入口。"""

# argparse 读取终端参数；asyncio 为终端中的异步运行创建事件循环。
import argparse
import asyncio

# Agent 编排一次运行；Model 是模型接口；UsageLimits 限制运行期间的模型请求。
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

# 共享配置负责创建真实模型客户端；离线测试会直接传入测试模型。
from pydantic_examples.config import build_model

# instructions 定义助手行为；PROMPT 是本次用户要问的具体问题。
PROMPT = "请用三句话解释：Agent 和普通聊天模型的区别是什么？"


def build_agent(model: Model) -> Agent[None, str]:
    # Agent[None, str] 表示不需要业务依赖，最终输出为字符串；创建 Agent 尚未请求模型。
    return Agent(model, instructions="你是 Python 教学助手。用简洁中文回答。")


async def run_async(agent: Agent[None, str], prompt: str):
    # await 等待整个 Agent 运行；一次运行可以包含多次请求，request_limit 不等于费用上限。
    return await agent.run(prompt, usage_limits=UsageLimits(request_limit=3))


def main() -> None:
    # --async 切换异步入口；dest 避免把 Python 关键字 async 用作参数属性名。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--async", dest="use_async", action="store_true")
    parser.add_argument("--prompt", default=PROMPT)
    args = parser.parse_args()
    # 到这里才加载 .env；导入本模块供测试复用时不会读取密钥。
    agent = build_agent(build_model())
    # 终端中用 asyncio.run 启动协程；Notebook 已有事件循环时应直接 await agent.run(...)。
    result = (
        asyncio.run(run_async(agent, args.prompt))
        if args.use_async
        else agent.run_sync(args.prompt, usage_limits=UsageLimits(request_limit=3))
    )
    # output 是最终回答；当前 PydanticAI 版本的 usage 是属性，不需要加括号调用。
    print(result.output)
    print("usage:", result.usage)


# 直接运行文件才执行 main；被 test.py 导入时只提供函数定义。
if __name__ == "__main__":
    main()

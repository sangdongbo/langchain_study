"""06：异步消费文字增量，最后读取完整结果。"""

# 流式读取是异步操作，终端入口用 asyncio 启动事件循环。
import asyncio

# Agent 负责运行；UsageLimits 同样适用于流式入口。
from pydantic_ai import Agent
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

# 通过共享配置创建模型客户端，API Key 不写在示例中。
from pydantic_examples.config import build_model

# 本课仅展示最终文字流，不包含工具调用的事件流。
PROMPT = "请用四条简短建议说明如何评审一项服务器采购。"


def build_agent(model: Model) -> Agent[None, str]:
    # 输出类型仍是 str；流式和非流式入口可以使用相同的 Agent 定义。
    return Agent(model, instructions="你是采购教学助手，用简洁中文回答。")


async def main() -> None:
    agent = build_agent(build_model())
    # 在异步上下文中消费流，退出上下文时由框架管理流资源。
    async with agent.run_stream(PROMPT, usage_limits=UsageLimits(request_limit=3)) as result:
        # delta=True 只返回新增文字；debounce_by=None 关闭时间合并，便于观察分块。
        # 默认的累计文字模式不能直接追加，否则前面的内容会被重复打印。
        async for delta in result.stream_text(delta=True, debounce_by=None):
            # 不换行并立即刷新终端，让已经收到的片段马上显示。
            print(delta, end="", flush=True)
        # 流消费结束后读取完整结果；此时打印的 usage 才包含完整的流式用量。
        output = await result.get_output()
        print("\n完整结果字符数：", len(output))
        print("usage:", result.usage)


# Notebook 中已有事件循环，应直接 await main()，而不是再次 asyncio.run。
if __name__ == "__main__":
    asyncio.run(main())

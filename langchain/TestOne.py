from dotenv import load_dotenv
from langchain.agents import create_agent

load_dotenv(override=True)


"""LangChain Agent 最小示例。

这个文件演示：
1. 定义一个普通 Python 函数作为工具。
2. 用 create_agent 创建能调用工具的 Agent。
3. 向 Agent 提问并打印最终回答。
"""


def get_weather(city: str) -> str:
    """获取指定城市的天气。

    这是演示工具，不会真的访问天气 API。
    """

    return f"{city}总是阳光明媚！"


# create_agent 会把模型、工具和系统提示词组合成一个可执行 Agent。
agent = create_agent(
    model="deepseek:deepseek-chat",
    tools=[get_weather],
    system_prompt="你是一个乐于助人的助手",
)

# 运行代理
result = agent.invoke(
    {"messages": [{"role": "user", "content": "旧金山的天气怎么样"}]}
)
# Agent 返回完整消息列表，最后一条通常是最终回复。
answer = result["messages"][-1].content
print(answer.encode("gbk", errors="replace").decode("gbk"))

from dotenv import load_dotenv
from langchain.agents import create_agent

load_dotenv(override=True)


def get_weather(city: str) -> str:
    """获取指定城市的天气。"""
    return f"{city}总是阳光明媚！"

agent = create_agent(
    model="deepseek:deepseek-chat",
    tools=[get_weather],
    system_prompt="你是一个乐于助人的助手",
)

# 运行代理
result = agent.invoke(
    {"messages": [{"role": "user", "content": "旧金山的天气怎么样"}]}
)
answer = result["messages"][-1].content
print(answer.encode("gbk", errors="replace").decode("gbk"))

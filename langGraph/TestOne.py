import os
from dotenv import load_dotenv
from langchain_deepseek import ChatDeepSeek
# 修改这里：从 langchain 引入新版的 create_agent
from langchain.agents import create_agent

load_dotenv(override=True)

def get_weather(city: str) -> str:
    """查询指定城市的天气。"""
    return f"{city} 今天晴。温度合适，穿短袖就可以了，天气不稳定，可能随时下雨，注意拿伞，随时查看天气预报"

model = ChatDeepSeek(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0,
)

# 新版的创建函数改为了 create_agent
agent = create_agent(
    model=model,
    tools=[get_weather],
    system_prompt="你是一个简洁可靠的助手。",
)

# 运行逻辑保持完全一致
response = agent.invoke(
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]}
)
print(response["messages"][-1].content)

# response1 = agent.ainvoke(
#     {"messages": [{"role": "user", "content": "上海天气怎么样？"}]}
# )
# print(response1)

# 将你的 for 循环改成这样：
for chunk in agent.stream(
        {"messages": [{"role": "user", "content": "上海天气怎么样"}]}
):
    # 1. 如果是大模型节点输出了内容
    if "model" in chunk:
        message = chunk["model"]["messages"][-1]
        # 如果包含工具调用
        if message.tool_calls:
            print(f"🤖 [AI 思考]: 需要调用工具 -> {message.tool_calls[0]['name']}({message.tool_calls[0]['args']})")
        # 如果是最终文本回答
        elif message.content:
            print(f"🤖 [AI 回答]: {message.content}")

    # 2. 如果是工具节点输出了内容
    elif "tools" in chunk:
        message = chunk["tools"]["messages"][-1]
        print(f"🛠️ [工具执行结果]: {message.content}")


# 注意：这里增加了 stream_mode="messages"
for chunk, metadata in agent.stream(
    {"messages": [{"role": "user", "content": "上海天气怎么样"}]},
    stream_mode="messages"
):
    # 如果是 AI 吐出的文本片段，并且类型是 AIMessageChunk
    if chunk.content and type(chunk).__name__ == "AIMessageChunk":
        # flush=True 让文字立刻蹦出来，不留缓冲区
        print(chunk.content, end="", flush=True)
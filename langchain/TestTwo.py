from dataclasses import dataclass
from dotenv import load_dotenv

from langchain.agents import create_agent
from langchain.chat_models import init_chat_model
from langchain.tools import tool, ToolRuntime
from langgraph.checkpoint.memory import InMemorySaver

load_dotenv(verbose=True)

# 定义系统提示
SYSTEM_PROMPT = """你是一位擅长用双关语表达的专家天气预报员。

你可以使用两个工具：

- get_weather_for_location：用于获取特定地点的天气
- get_user_location：用于获取用户的位置

如果用户询问天气，请确保你知道具体位置。如果从问题中可以判断他们指的是自己所在的位置，请使用 get_user_location 工具来查找他们的位置。"""

# 定义上下文模式
@dataclass
class Context:
    """自定义运行时上下文模式。"""
    user_id: str

# 定义工具
@tool
def get_weather_for_location(city: str) -> str:
    """获取指定城市的天气。"""
    return f"{city}总是阳光明媚！"

@tool
def get_user_location(runtime: ToolRuntime[Context]) -> str:
    """根据用户 ID 获取用户信息。"""
    user_id = runtime.context.user_id
    return "Florida" if user_id == "1" else "SF"

# 配置模型
model = init_chat_model(
    "deepseek:deepseek-chat",
    temperature=0
)

# 定义响应格式
@dataclass
class ResponseFormat:
    """代理的响应模式。"""
    # 带双关语的回应（始终必需）
    punny_response: str
    # 天气的任何有趣信息（如果有）
    weather_conditions: str | None = None

# 设置记忆
checkpointer = InMemorySaver()

# 创建代理
agent = create_agent(
    model=model,
    system_prompt=SYSTEM_PROMPT,
    tools=[get_user_location, get_weather_for_location],
    context_schema=Context,
    response_format=ResponseFormat,
    checkpointer=checkpointer
)

# 运行代理
# `thread_id` 是给定对话的唯一标识符。
config = {"configurable": {"thread_id": "1"}}

response = agent.invoke(
    {"messages": [{"role": "user", "content": "外面的天气怎么样？"}]},
    config=config,
    context=Context(user_id="1")
)

print(response['structured_response'])
# ResponseFormat(
#     punny_response="佛罗里达今天依然是'阳光灿烂'的一天！阳光正在播放'rey-dio'热门歌曲！我得说，这是进行'solar-bration'的完美天气！如果你希望下雨，恐怕这个想法已经'被冲走'了——预报仍然'清晰地'灿烂！",
#     weather_conditions="佛罗里达总是阳光明媚！"
# )

# 注意，我们可以使用相同的 `thread_id` 继续对话。
response = agent.invoke(
    {"messages": [{"role": "user", "content": "谢谢！"}]},
    config=config,
    context=Context(user_id="1")
)

print(response['structured_response'])
# ResponseFormat(
#     punny_response="你真是'雷'厉风行地欢迎！帮助你保持'当前'天气总是'轻而易举'。我只是'云'游四方，等待随时'淋浴'你更多预报。祝你在佛罗里达的阳光下度过'sun-sational'的一天！",
#     weather_conditions=None
# )
from __future__ import annotations

"""学习用 LangChain tools。

这些工具是 LangChain `BaseTool`，不是普通 Python 函数。
它们模拟真实 Agent 会调用的外部能力，例如用户信息、位置、天气、外部数据。
第一版不接真实接口，原因有两个：
- 本地学习演示更稳定，不受网络和第三方 API 影响。
- 学习重点是“Agent 如何调用工具”，不是具体业务系统接入。

所有工具都返回统一结构：
{
    "source": "mock_tool",
    "data": {...}
}
这样 Agent 和页面可以用同一种方式处理工具结果。
"""

from datetime import datetime
from typing import Any

from langchain_core.tools import BaseTool, tool


@tool("get_user_id")
def get_user_id() -> dict[str, Any]:
    """返回演示用户 ID。"""

    return {"source": "mock_tool", "data": {"user_id": "U1001", "name": "演示用户"}}


@tool("get_user_location")
def get_user_location() -> dict[str, Any]:
    """返回演示用户位置。"""

    return {"source": "mock_tool", "data": {"city": "上海", "district": "浦东新区"}}


@tool("get_current_month")
def get_current_month() -> dict[str, Any]:
    """返回当前月份。

    这个工具展示“无需模型也能准确完成”的确定性能力。
    """

    now = datetime.now()
    return {"source": "mock_tool", "data": {"month": now.strftime("%Y-%m"), "month_number": now.month}}


@tool("get_weather")
def get_weather(location: str = "上海") -> dict[str, Any]:
    """返回 mock 天气。

    参数 location 由 Agent 从用户问题中抽取，例如“北京天气”。
    """

    return {
        "source": "mock_tool",
        "data": {
            "location": location,
            "condition": "多云",
            "temperature": "24°C",
            "suggestion": "适合进行智能体项目学习。",
        },
    }


@tool("generate_external_data")
def generate_external_data(topic: str) -> dict[str, Any]:
    """生成 mock 外部数据。

    真实项目里这里可能是 ERP、CRM、HTTP API、数据库查询等。
    这里返回固定结构，方便观察工具调用日志和 Agent 输出。
    """

    return {
        "source": "mock_tool",
        "data": {
            "topic": topic,
            "items": [f"{topic} 指标 A", f"{topic} 指标 B", f"{topic} 指标 C"],
        },
    }


ALL_TOOLS: list[BaseTool] = [
    get_user_id,
    get_user_location,
    get_current_month,
    get_weather,
    generate_external_data,
]
TOOLS_BY_NAME: dict[str, BaseTool] = {tool_item.name: tool_item for tool_item in ALL_TOOLS}


def list_tools() -> list[BaseTool]:
    """返回所有可绑定给 LangChain Agent 或模型的工具对象。"""

    return ALL_TOOLS


def get_tool(name: str) -> BaseTool:
    """按名称获取工具。"""

    return TOOLS_BY_NAME[name]


def run_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """执行工具并返回结构化结果。

    ReactAgent 通过这个函数调用工具，后续如果换成 LangGraph/tool-calling，
    也可以复用同一批 BaseTool。
    """

    result = get_tool(name).invoke(arguments or {})
    if isinstance(result, dict):
        return result
    return {"source": "tool", "data": result}

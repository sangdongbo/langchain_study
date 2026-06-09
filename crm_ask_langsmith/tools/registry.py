from __future__ import annotations

from typing import Any

from langchain_core.tools import BaseTool

from crm_ask_langsmith.tools.approval_tools import create_approval_request
from crm_ask_langsmith.tools.leave_tools import create_leave_request, get_leave_balance


# 所有可供 ERP Agent 使用的 LangChain tools 都在这里注册。
# 后续新增流程时，只需要新增一个 tools/*.py 文件，并把 tool 放进 ALL_TOOLS。
ALL_TOOLS: list[BaseTool] = [
    get_leave_balance,
    create_leave_request,
    create_approval_request,
]
TOOLS_BY_NAME: dict[str, BaseTool] = {tool.name: tool for tool in ALL_TOOLS}


def list_tools() -> list[BaseTool]:
    """返回可绑定给 LLM 的 LangChain tools。

    bind_tools(list_tools()) 会把这些函数的名称、参数和描述交给模型。
    """

    return ALL_TOOLS


def get_tool(name: str) -> BaseTool:
    """按名称获取一个 LangChain tool。

    tool.name 来自 @tool("name") 装饰器。
    """

    return TOOLS_BY_NAME[name]


def run_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    """执行指定 LangChain tool，并补充 tool 名称方便调试和测试。

    页面不会把 tool 名称直接展示给用户；Agent 会把结构化结果转成业务话术。
    """

    result = get_tool(name).invoke(arguments or {})
    if isinstance(result, dict):
        return {"tool": name, **result}
    return {"tool": name, "source": "tool", "data": result}

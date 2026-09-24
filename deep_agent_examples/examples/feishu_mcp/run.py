"""使用外部飞书 MCP Server 的 Deep Agent 示例。

系统 Codex 中的 ``mcp__lark_mcp__...`` 是宿主进程内置工具；Python 进程不能
直接调用它们。本例通过 ``MCPAdapter`` 连接一个独立的 HTTP MCP Server，再把
发现到的只读飞书工具交给 Deep Agent。
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
from collections.abc import Iterable
from typing import Any
from uuid import uuid4

from deepagents import create_deep_agent
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    load_environment,
    tracing_enabled,
    tracing_project,
)

# 这些后缀对应系统 Codex 飞书 MCP 中的只读能力。不同 MCP Server 可能给工具
# 加上 lark_、feishu_ 等前缀，所以过滤时使用“完整名或后缀”匹配。
READ_ONLY_TOOL_SUFFIXES = frozenset(
    {
        "docx_builtin_search",
        "docx_v1_document_rawContent",
        "wiki_v1_node_search",
        "wiki_v2_space_getNode",
        "im_v1_message_list",
        "bitable_v1_appTableRecord_search",
    }
)


def _tool_name(tool: Any) -> str:
    """读取 LangChain/MCP 工具名称，不假设具体工具类。"""

    return str(getattr(tool, "name", ""))


def _matches_read_only(name: str) -> bool:
    """判断工具是否属于允许自动调用的飞书只读能力。"""

    return any(name == suffix or name.endswith(f"_{suffix}") for suffix in READ_ONLY_TOOL_SUFFIXES)


def select_tools(
    tools: Iterable[Any], *, allow_all: bool = False
) -> tuple[list[Any], list[str]]:
    """按安全白名单选择工具，并返回被过滤掉的工具名。

    默认拒绝消息发送、Bitable 写入和权限修改等副作用工具；只有显式设置
    ``FEISHU_MCP_ALLOW_ALL_TOOLS=true`` 才会把服务器发现的全部工具交给 Agent。
    """

    discovered = list(tools)
    if allow_all:
        return discovered, []

    selected: list[Any] = []
    rejected: list[str] = []
    for tool in discovered:
        name = _tool_name(tool)
        if _matches_read_only(name):
            selected.append(tool)
        else:
            rejected.append(name or "<unnamed>")
    return selected, rejected


def _headers_from_environment() -> dict[str, str]:
    """解析可选请求头，避免把飞书 Token 写进代码或日志。"""

    raw = os.getenv("FEISHU_MCP_HEADERS_JSON", "").strip()
    if not raw:
        return {}
    try:
        headers = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise RuntimeError("FEISHU_MCP_HEADERS_JSON 必须是 JSON 对象。") from exc
    if not isinstance(headers, dict) or not all(
        isinstance(key, str) and isinstance(value, str)
        for key, value in headers.items()
    ):
        raise RuntimeError("FEISHU_MCP_HEADERS_JSON 必须是字符串键和值组成的 JSON 对象。")
    return headers


def mcp_target() -> str | dict[str, Any]:
    """构造 FastMCP 可识别的 HTTP URL 或带请求头的 MCP 配置。"""

    load_environment()
    url = os.getenv("FEISHU_MCP_URL", "").strip()
    if not url:
        raise RuntimeError(
            "未配置 FEISHU_MCP_URL。请在 .env 中填写外部飞书 MCP Server 的 http(s) 地址。"
        )
    if not url.startswith(("http://", "https://")):
        raise RuntimeError("FEISHU_MCP_URL 必须是 http:// 或 https:// 地址。")

    headers = _headers_from_environment()
    if not headers:
        return url
    # FastMCP 的标准 MCPConfig 形式；headers 只在进程内传递，不打印到终端。
    return {"mcpServers": {"feishu": {"url": url, "headers": headers}}}


def _allow_all_tools() -> bool:
    """读取危险的全工具开关；默认始终关闭。"""

    return os.getenv("FEISHU_MCP_ALLOW_ALL_TOOLS", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


async def run(prompt: str) -> None:
    """发现飞书工具、构建 Agent 并执行一次文档检索任务。"""

    try:
        from langchain.mcp import MCPAdapter
    except ImportError as exc:
        raise RuntimeError(
            "MCP 依赖未安装。请先执行 `uv sync --extra mcp`，再运行本例。"
        ) from exc

    target = mcp_target()
    async with MCPAdapter(target) as adapter:
        discovered = await adapter.list_tools()
        tools, rejected = select_tools(discovered, allow_all=_allow_all_tools())
        if not tools:
            names = ", ".join(_tool_name(tool) for tool in discovered) or "(服务器未返回工具)"
            raise RuntimeError(
                "没有发现可用的只读飞书工具。已发现工具：" + names +
                "。如果确认服务器安全，可临时设置 FEISHU_MCP_ALLOW_ALL_TOOLS=true。"
            )

        agent = create_deep_agent(
            model=build_model(),
            tools=tools,
            name="feishu-mcp-agent",
            system_prompt=(
                "你是飞书资料检索助手。只使用已提供的只读工具搜索飞书文档、Wiki、"
                "消息或多维表格，并用中文给出带证据的简洁总结；不要发送消息、修改记录或"
                "修改权限。"
            ),
        )
        thread_id = f"feishu-mcp-{uuid4().hex[:8]}"
        config = invoke_config("feishu-mcp", thread_id)
        with tracing_context(
            enabled=tracing_enabled(),
            project_name=tracing_project(),
            tags=["deep-agent-example", "feishu-mcp"],
            metadata=config["metadata"],
        ):
            result = await agent.ainvoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config=config,
            )

    print("发现工具：", ", ".join(_tool_name(tool) for tool in discovered))
    print("实际启用：", ", ".join(_tool_name(tool) for tool in tools))
    if rejected:
        print("已过滤写操作或未知工具：", ", ".join(rejected))
    print("\nAgent 结果：")
    print(getattr(result["messages"][-1], "content", result["messages"][-1]))
    print(f"thread_id: {thread_id}")


def main() -> None:
    """解析一次飞书检索任务；默认只允许只读工具。"""

    parser = argparse.ArgumentParser(description="Run the Feishu MCP Deep Agent example.")
    parser.add_argument(
        "--prompt",
        default="搜索飞书中与采购评审流程有关的文档，并总结关键步骤和文档证据。",
        help="交给飞书只读 MCP 工具的中文检索任务。",
    )
    args = parser.parse_args()
    asyncio.run(run(args.prompt))


if __name__ == "__main__":
    main()

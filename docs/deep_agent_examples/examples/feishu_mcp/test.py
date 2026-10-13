"""飞书 MCP 逻辑的离线测试，不需要 Key、网络或真实 MCP Server。"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from langchain_core.messages import AIMessage, ToolMessage  # noqa: E402
from langchain_core.tools import tool  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)
from examples.feishu_mcp.run import mcp_target, select_tools  # noqa: E402


@tool("docx_builtin_search")
def fake_search(query: str) -> str:
    """模拟飞书文档搜索结果。"""

    return json.dumps(
        {"query": query, "documents": [{"token": "doc-001", "title": "采购评审流程"}]},
        ensure_ascii=False,
    )


@tool("docx_v1_document_rawContent")
def fake_read(document_id: str) -> str:
    """模拟读取飞书文档正文。"""

    return f"{document_id}: 先核对预算，再核验供应商，最后提交审批。"


def main() -> None:
    """验证白名单、工具循环和最终中文总结。"""

    configure_utf8_output()
    discovered = [
        SimpleNamespace(name="lark_docx_builtin_search"),
        SimpleNamespace(name="lark_docx_v1_document_rawContent"),
        SimpleNamespace(name="lark_im_v1_message_create"),
    ]
    selected, rejected = select_tools(discovered)
    assert [tool.name for tool in selected] == [
        "lark_docx_builtin_search",
        "lark_docx_v1_document_rawContent",
    ]
    assert rejected == ["lark_im_v1_message_create"]

    os.environ["FEISHU_MCP_URL"] = "https://feishu-mcp.example.test/mcp"
    os.environ.pop("FEISHU_MCP_HEADERS_JSON", None)
    assert mcp_target() == "https://feishu-mcp.example.test/mcp"

    model = ToolCapableFakeModel(
        responses=[
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "docx_builtin_search",
                        "args": {"query": "采购评审流程"},
                        "id": "feishu-search-1",
                    }
                ],
            ),
            AIMessage(
                content="",
                tool_calls=[
                    {
                        "name": "docx_v1_document_rawContent",
                        "args": {"document_id": "doc-001"},
                        "id": "feishu-read-1",
                    }
                ],
            ),
            AIMessage(content="已找到采购评审流程：先核对预算，再核验供应商，最后提交审批。"),
        ]
    )
    agent = create_deep_agent(
        model=model,
        tools=[fake_search, fake_read],
        name="feishu-mcp-test-agent",
    )
    result = agent.invoke(
        {"messages": [{"role": "user", "content": "搜索并读取采购评审流程。"}]}
    )
    tool_messages = [
        message for message in result["messages"] if isinstance(message, ToolMessage)
    ]
    assert len(tool_messages) == 2
    assert result["messages"][-1].content.startswith("已找到采购评审流程")
    print("Feishu MCP 离线测试通过")
    print("- MCP 工具名称按后缀匹配，兼容 lark_/feishu_ 前缀")
    print("- 默认过滤消息发送等写操作")
    print("- Agent 完成文档搜索、正文读取和中文总结")


if __name__ == "__main__":
    main()

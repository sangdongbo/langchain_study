from __future__ import annotations

import os
from typing import Any
from collections.abc import Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage
from langchain_deepseek import ChatDeepSeek
from openai import APIConnectionError, APIStatusError, APITimeoutError

from common.chat_store import ChatMessage
from erp_ask.tools.registry import get_tool, list_tools


# v2 使用自己的 LLM 配置和系统 prompt，不复用 common.llm。
# 这样 ERP Agent 的提示词可以独立演进，不影响原始聊天示例。
def build_llm() -> ChatDeepSeek:
    """根据环境变量创建 DeepSeek 聊天模型。"""

    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("请先在 .env 中配置 DEEPSEEK_API_KEY，再发送消息。")
    return ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=api_key,
        temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0.7")),
        timeout=30,
        max_retries=1,
    )


def build_tool_bound_llm():
    """创建已绑定 LangChain tools 的 DeepSeek 模型。

    模型可以根据 prompt 自己产生 tool_calls；调用和结果回填在
    invoke_with_tools() 中完成。
    """

    return build_llm().bind_tools(list_tools())


def build_prompt_messages(
    title: str, persona: str, messages: list[ChatMessage]
) -> list[SystemMessage | HumanMessage | AIMessage]:
    """构造 v2 专用 prompt。

    ERP 数据必须由工具层返回；这里的提示词只约束普通 LLM 回复，
    不承担真实业务查询。
    """

    assistant_name = title.strip() or "ERP助手"
    prompt_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(
            content=(
                "你是 Streamlit v2 页面中的 ERP 聊天 Agent。"
                f"你的昵称是：{assistant_name}。你的人设是：{persona} "
                f"用户询问你的名字时，必须承认这个昵称，并明确说你叫{assistant_name}。"
                "即使历史消息里出现过其他名字，也必须以当前昵称为准。"
                "你可以回答普通问题，但遇到请假、审批、假期余额等 ERP 业务时要保持克制。"
                "不要编造假期余额、审批编号、审批状态、员工信息或业务数据；"
                "这些数据必须由 ERP 工具返回。"
                "如果聊天记录里已经出现 ERP 查询或审批结果，可以基于该结果解释，"
                "但不要自行补充新的业务事实。"
                "请用中文自然回复，保持简洁、直接、友好。"
            )
        )
    ]
    for message in messages[-12:]:
        if message.role == "user":
            prompt_messages.append(HumanMessage(content=message.content))
        elif message.role == "assistant":
            prompt_messages.append(AIMessage(content=message.content))
    return prompt_messages


def stream_deepseek(title: str, persona: str, messages: list[ChatMessage]) -> Iterator[str]:
    """调用已绑定 tools 的 DeepSeek，并把最终回复按字符串输出。

    ERP 表单式流程仍由 agent/erp_agent.py 先拦截；没有被规则命中的普通问题
    会走这里。如果模型决定调用工具，invoke_with_tools() 会执行 LangChain tool，
    再让模型基于工具结果生成用户可读回复。
    """

    prompt_messages = build_prompt_messages(title, persona, messages)
    try:
        yield _message_content_to_text(invoke_with_tools(prompt_messages))
    except APITimeoutError as exc:
        raise RuntimeError("连接 DeepSeek 超时，请稍后再试。") from exc
    except APIConnectionError as exc:
        raise RuntimeError("无法连接 DeepSeek，请检查网络或代理。") from exc
    except APIStatusError as exc:
        raise RuntimeError(f"DeepSeek API 返回错误：{exc.status_code}") from exc


def invoke_with_tools(messages: list[SystemMessage | HumanMessage | AIMessage]) -> AIMessage:
    """执行一次 LangChain function calling 回合。

    1. 先让绑定 tools 的模型判断是否需要工具。
    2. 如果没有 tool_calls，直接返回模型消息。
    3. 如果有 tool_calls，逐个执行 registry 中的 LangChain tool。
    4. 把 ToolMessage 追加回上下文，让模型生成最终自然语言答复。
    """

    llm = build_tool_bound_llm()
    first_response = llm.invoke(messages)
    tool_calls = getattr(first_response, "tool_calls", None) or []
    if not tool_calls:
        return first_response

    tool_messages = [_run_tool_call(tool_call) for tool_call in tool_calls]
    final_response = llm.invoke([*messages, first_response, *tool_messages])
    return final_response


def _run_tool_call(tool_call: dict[str, Any]) -> ToolMessage:
    """执行模型返回的单个 tool call，并转成 LangChain ToolMessage。"""

    tool_name = tool_call["name"]
    arguments = tool_call.get("args") or {}
    result = get_tool(tool_name).invoke(arguments)
    return ToolMessage(
        content=str(result),
        tool_call_id=tool_call["id"],
        name=tool_name,
    )


def _message_content_to_text(message: AIMessage) -> str:
    content = message.content
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item) for item in content)
    return str(content)

from __future__ import annotations

import os
from collections.abc import Iterator

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from openai import APIConnectionError, APIStatusError, APITimeoutError

from common.chat_store import ChatMessage


"""共享的 DeepSeek 调用封装。

页面层只关心“给我一段流式文本”，不直接处理 API Key、模型参数或异常。
这些细节集中放在这里，后续换模型时只改这个模块即可。
"""


def build_llm() -> ChatDeepSeek:
    """根据 `.env` 创建 DeepSeek 聊天模型对象。"""

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


def build_prompt_messages(
    title: str, persona: str, messages: list[ChatMessage]
) -> list[SystemMessage | HumanMessage | AIMessage]:
    """把本地 ChatMessage 转成 LangChain 模型需要的消息对象。"""

    assistant_name = title.strip() or "小黑"
    prompt_messages: list[SystemMessage | HumanMessage | AIMessage] = [
        SystemMessage(
            content=(
                "你是一个 Streamlit 页面中的 AI 智能助手。"
                f"你的昵称是：{assistant_name}。你的人设是：{persona} "
                f"用户询问你的名字时，必须承认这个昵称，并明确说你叫{assistant_name}。"
                "即使历史消息里出现过其他名字，也必须以当前昵称为准。"
                "不要否认这个昵称，不要说这是别人的艺名。"
                "请用中文自然回复，保持简洁、直接、友好。"
            )
        )
    ]
    for message in messages[-12:]:
        # 只带最近 12 条消息，避免上下文无限增长导致请求变慢或超限。
        if message.role == "user":
            prompt_messages.append(HumanMessage(content=message.content))
        elif message.role == "assistant":
            prompt_messages.append(AIMessage(content=message.content))
    return prompt_messages


def stream_deepseek(title: str, persona: str, messages: list[ChatMessage]) -> Iterator[str]:
    """流式调用 DeepSeek。

    yield 会一段一段返回文本，Streamlit 页面可以边收到边刷新显示。
    """

    llm = build_llm()
    prompt_messages = build_prompt_messages(title, persona, messages)
    try:
        for chunk in llm.stream(prompt_messages):
            content = chunk.content
            if isinstance(content, str):
                yield content
            elif isinstance(content, list):
                yield "".join(str(item) for item in content)
    except APITimeoutError as exc:
        raise RuntimeError("连接 DeepSeek 超时，请稍后再试。") from exc
    except APIConnectionError as exc:
        raise RuntimeError("无法连接 DeepSeek，请检查网络或代理。") from exc
    except APIStatusError as exc:
        raise RuntimeError(f"DeepSeek API 返回错误：{exc.status_code}") from exc

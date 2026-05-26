from __future__ import annotations

"""环境配置读取。

这个模块只负责把环境变量整理成结构化配置，不直接创建模型。
模型创建放在 `model/factory.py`，这样职责更清晰：
- settings.py：读配置。
- factory.py：根据配置创建对象。
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDemoSettings:
    """智能体 demo 运行所需的配置。"""

    chat_provider: str
    chat_api_key: str | None
    chat_model: str
    openai_base_url: str | None
    embedding_provider: str
    embedding_model: str
    temperature: float


def load_settings() -> AgentDemoSettings:
    """从环境变量加载配置。

    优先 DeepSeek：因为项目示例主要用 DeepSeek chat model。
    如果没有 DEEPSEEK_API_KEY，则回退到 OpenAI-compatible 配置。
    """

    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    temperature = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2"))

    if deepseek_key:
        # DeepSeek 分支不需要 openai_base_url。
        return AgentDemoSettings(
            chat_provider="deepseek",
            chat_api_key=deepseek_key,
            chat_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            openai_base_url=None,
            embedding_provider=os.getenv("RAG_EMBEDDING_PROVIDER", "local").lower(),
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            temperature=temperature,
        )

    # OpenAI-compatible 分支既可以指向 OpenAI，也可以指向兼容接口的其它服务。
    return AgentDemoSettings(
        chat_provider="openai",
        chat_api_key=os.getenv("OPENAI_API_KEY"),
        chat_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        embedding_provider=os.getenv("RAG_EMBEDDING_PROVIDER", "local").lower(),
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        temperature=temperature,
    )

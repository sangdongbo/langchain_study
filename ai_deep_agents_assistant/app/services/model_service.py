from __future__ import annotations

import os

from langchain_openai import ChatOpenAI

from ai_deep_agents_assistant.app.services.env_config import (
    deepseek_base_url,
    load_project_env,
)


def build_chat_model() -> ChatOpenAI:
    """Build the real DeepSeek chat model used by Deep Agents."""
    load_project_env()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("请先在 .env 中配置 DEEPSEEK_API_KEY。")

    return ChatOpenAI(
        model=os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-chat",
        api_key=api_key,
        base_url=deepseek_base_url(),
        temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0")),
        timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "120")),
        max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "2")),
    )

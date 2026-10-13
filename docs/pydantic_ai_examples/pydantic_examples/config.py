"""读取现有模型配置；导入模块不会加载密钥或发出请求。"""

import os
from pathlib import Path

from dotenv import load_dotenv
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

PROJECT_DIR = Path(__file__).resolve().parents[1]


def load_environment() -> None:
    for path in (
        PROJECT_DIR / ".env",
        PROJECT_DIR.parents[1] / ".env",
        PROJECT_DIR.parent / "deep_agent_examples" / ".env",
    ):
        load_dotenv(path, override=False)


def build_model() -> OpenAIChatModel:
    load_environment()
    for prefix, default_url, default_model in (
        ("LLM", "https://api.openai.com/v1", "gpt-4o-mini"),
        ("DEEPSEEK", "https://api.deepseek.com/v1", "deepseek-chat"),
        ("OPENAI", "https://api.openai.com/v1", "gpt-4o-mini"),
    ):
        key = os.getenv(f"{prefix}_API_KEY", "").strip()
        if key:
            return OpenAIChatModel(
                os.getenv(f"{prefix}_MODEL") or default_model,
                provider=OpenAIProvider(
                    api_key=key,
                    base_url=os.getenv(f"{prefix}_BASE_URL") or default_url,
                ),
                settings={"temperature": 0, "timeout": 60},
            )
    raise RuntimeError("请在 .env 配置 LLM_API_KEY、DEEPSEEK_API_KEY 或 OPENAI_API_KEY。")

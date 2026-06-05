from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_env() -> None:
    """Load the project .env from the current directory or its parents."""

    current = Path.cwd().resolve()
    for path in [current, *current.parents]:
        env_path = path / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
            return


def build_deepseek_model():
    """Create a DeepSeek chat model when credentials are available."""

    load_env()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        return None

    from langchain_deepseek import ChatDeepSeek

    return ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=api_key,
        temperature=0,
        timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "60")),
        max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "2")),
    )


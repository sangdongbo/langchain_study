from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI


PROJECT_DIR = Path(__file__).resolve().parents[1]
REPOSITORY_DIR = PROJECT_DIR.parent


def load_environment() -> None:
    """Load the example-specific env first, then the repository fallback."""
    load_dotenv(PROJECT_DIR / ".env", override=False)
    load_dotenv(REPOSITORY_DIR / ".env", override=False)


@dataclass(frozen=True)
class ModelSettings:
    api_key: str
    base_url: str | None
    model: str
    temperature: float
    timeout: float


def model_settings() -> ModelSettings:
    load_environment()
    api_key = (
        os.getenv("LLM_API_KEY")
        or os.getenv("DEEPSEEK_API_KEY")
        or os.getenv("OPENAI_API_KEY")
        or ""
    )
    if not api_key:
        raise RuntimeError(
            "Missing model credential. Copy .env.example to .env and set "
            "LLM_API_KEY, DEEPSEEK_API_KEY, or OPENAI_API_KEY."
        )

    base_url = (
        os.getenv("LLM_BASE_URL")
        or os.getenv("DEEPSEEK_BASE_URL")
        or os.getenv("OPENAI_BASE_URL")
        or None
    )
    model = (
        os.getenv("LLM_MODEL")
        or os.getenv("DEEPSEEK_MODEL")
        or os.getenv("OPENAI_MODEL")
        or "deepseek-chat"
    )
    return ModelSettings(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=float(os.getenv("LLM_TEMPERATURE", "0")),
        timeout=float(os.getenv("LLM_TIMEOUT", "120")),
    )


def build_model() -> ChatOpenAI:
    settings = model_settings()
    return ChatOpenAI(
        model=settings.model,
        api_key=settings.api_key,
        base_url=settings.base_url,
        temperature=settings.temperature,
        timeout=settings.timeout,
        max_retries=2,
    )


def tracing_enabled() -> bool:
    load_environment()
    return os.getenv("LANGSMITH_TRACING", "false").strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


def tracing_project() -> str:
    load_environment()
    return os.getenv("LANGSMITH_PROJECT") or "deep-agent-examples"


def invoke_config(example: str, thread_id: str) -> dict:
    return {
        "configurable": {"thread_id": thread_id},
        "tags": ["deep-agent-example", example],
        "metadata": {
            "example": example,
            "project_kind": "deep-agent-learning",
        },
        "run_name": f"deep-agent-example:{example}",
    }

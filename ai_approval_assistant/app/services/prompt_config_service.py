from __future__ import annotations
import json
import os
from functools import lru_cache
from pathlib import Path
from typing import Any
from pydantic import BaseModel, Field, ValidationError

DEFAULT_PROMPT_FILE = (
    Path(__file__).resolve().parents[2] / "prompts" / "approval_prompts.json"
)
PROMPT_FILE_ENV = "AI_APPROVAL_PROMPT_FILE"


class PromptSection(BaseModel):
    """单个模型辅助任务的提示词配置块。"""

    system: str
    output_schema: dict[str, Any] = Field(default_factory=dict)
    rules: list[str] = Field(default_factory=list)


class DecisionReviewPromptSection(PromptSection):
    """有界路由复核的提示词配置块。"""

    allowed_routes: list[str] = Field(
        default_factory=lambda: ["collect", "submit", "cancel", "clarify"]
    )


class ApprovalPromptConfig(BaseModel):
    """从 JSON 加载的完整提示词配置。"""

    version: str = "local"
    classification: PromptSection
    slot_extraction: PromptSection
    decision_review: DecisionReviewPromptSection


def get_prompt_config() -> ApprovalPromptConfig:
    """返回当前生效的提示词配置。"""
    return _load_prompt_config(_resolve_prompt_file())


def get_prompt_config_path() -> Path:
    """返回解析后的提示词配置文件路径。"""
    return _resolve_prompt_file()


def reload_prompt_config() -> ApprovalPromptConfig:
    """清空提示词缓存并从磁盘重新加载配置。"""
    _load_prompt_config.cache_clear()
    return get_prompt_config()


def _resolve_prompt_file() -> Path:
    """从环境变量或默认位置解析提示词文件。"""
    configured = os.getenv(PROMPT_FILE_ENV)
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_PROMPT_FILE


@lru_cache(maxsize=8)
def _load_prompt_config(path: Path) -> ApprovalPromptConfig:
    """从 JSON 文件加载并校验提示词配置。"""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return ApprovalPromptConfig.model_validate(payload)
    except FileNotFoundError as exc:
        raise RuntimeError(f"Prompt config file not found: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Prompt config file is not valid JSON: {path}") from exc
    except ValidationError as exc:
        raise RuntimeError(f"Prompt config schema is invalid: {path}") from exc

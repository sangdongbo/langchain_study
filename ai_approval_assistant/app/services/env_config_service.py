from __future__ import annotations
from pathlib import Path

from dotenv import load_dotenv


def ai_approval_project_root() -> Path:
    """返回 AI 审批助手独立项目根目录。"""
    return Path(__file__).resolve().parents[2]


def load_ai_approval_env() -> None:
    """加载 AI 审批助手项目内的 .env 文件。"""
    load_dotenv(ai_approval_project_root() / ".env")

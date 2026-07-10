from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv


def load_project_env() -> Path | None:
    """Load .env from this project or its parent repository if present."""
    current = Path.cwd().resolve()
    candidates = [current, *current.parents]
    project_dir = Path(__file__).resolve().parents[2]
    candidates.insert(0, project_dir)

    for directory in candidates:
        env_path = directory / ".env"
        if env_path.exists():
            load_dotenv(env_path, override=False)
            return env_path
    return None


def deepseek_base_url() -> str:
    """Return DeepSeek-compatible base URL."""
    return os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"


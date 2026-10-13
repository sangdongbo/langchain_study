"""演示产物与 browser-use 的本地浏览器配置。"""

import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")

PROJECT_DIR = Path(__file__).resolve().parents[1]


def artifacts(example: str) -> Path:
    directory = PROJECT_DIR / ".artifacts" / example
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def run_artifacts(example: str) -> Path:
    """为一次 Agent 运行创建独立目录，避免旧结果冒充本次结果。"""
    run_id = f"{datetime.now().astimezone():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
    directory = artifacts(example) / run_id
    directory.mkdir()
    write_run_status(directory, "running")
    return directory


def write_run_status(directory: Path, status: str, error: Exception | None = None) -> None:
    payload = {"status": status}
    if error is not None:
        payload["error"] = f"{type(error).__name__}: {error}"
    (directory / "status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def create_session(headless: bool):
    from browser_use import BrowserProfile, BrowserSession
    from playwright.async_api import async_playwright

    async with async_playwright() as playwright:
        executable = playwright.chromium.executable_path
    if not Path(executable).is_file():
        raise RuntimeError("请先运行 uv run playwright install chromium。")
    return BrowserSession(
        browser_profile=BrowserProfile(
            executable_path=executable,
            headless=headless,
            allowed_domains=["127.0.0.1"],
            enable_default_extensions=False,
            use_cloud=False,
            keep_alive=True,
        )
    )

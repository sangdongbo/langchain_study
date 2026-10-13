"""演示产物与 browser-use 的本地浏览器配置。"""

import json
import os
from datetime import datetime
from pathlib import Path
from uuid import uuid4

# 默认关闭匿名遥测；setdefault 保留用户已经显式设置的值。
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")

PROJECT_DIR = Path(__file__).resolve().parents[1]


def artifacts(example: str) -> Path:
    # 01、02 把截图和 trace 保存到固定目录；同名文件会被下一次演示覆盖。
    directory = PROJECT_DIR / ".artifacts" / example
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def run_artifacts(example: str) -> Path:
    """为一次 Agent 运行创建独立目录，避免旧结果冒充本次结果。"""
    # 时间戳方便定位运行时间，随机后缀降低同一秒内目录重名的概率。
    run_id = f"{datetime.now().astimezone():%Y%m%d-%H%M%S}-{uuid4().hex[:8]}"
    directory = artifacts(example) / run_id
    directory.mkdir()
    # 先记录 running；运行入口负责在结束时改写为 success 或 failed。
    write_run_status(directory, "running")
    return directory


def write_run_status(directory: Path, status: str, error: Exception | None = None) -> None:
    # 状态文件描述本次运行；有 history.json 并不等于任务已验收成功。
    payload = {"status": status}
    if error is not None:
        payload["error"] = f"{type(error).__name__}: {error}"
    # 保留中文便于直接阅读；异常信息只用于本地排查，不应公开敏感产物。
    (directory / "status.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )


async def create_session(headless: bool):
    # 延迟导入浏览器依赖，基础静态检查不需要创建 browser-use 会话。
    from browser_use import BrowserProfile, BrowserSession
    from playwright.async_api import async_playwright

    # 这里只取得 Playwright 已安装的 Chromium 路径，不启动 Playwright 浏览器。
    async with async_playwright() as playwright:
        executable = playwright.chromium.executable_path
    # 缺少浏览器时给出安装指令，不自动下载或回退到云浏览器。
    if not Path(executable).is_file():
        raise RuntimeError("请先运行 uv run playwright install chromium。")
    # 浏览器的实际启动与操作交给 browser-use，避免同时维护两套浏览器实例。
    return BrowserSession(
        browser_profile=BrowserProfile(
            executable_path=executable,
            headless=headless,
            allowed_domains=["127.0.0.1"],  # 限制可导航域名，不等同于完整网络沙箱。
            enable_default_extensions=False,  # 演示无需安装默认扩展。
            use_cloud=False,  # 使用本机 Chromium，不连接 browser-use 云浏览器。
            keep_alive=True,  # 由运行入口在 finally 中显式关闭会话。
        )
    )

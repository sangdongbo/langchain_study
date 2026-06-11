from __future__ import annotations
import json
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger("ai_approval_assistant.debug")


def write_debug_log(event: str, payload: dict[str, Any]) -> None:
    """写入 AI 审批调试日志，并在写入前脱敏敏感字段。"""
    sanitized_payload = sanitize_payload(payload)
    logger.info("%s %s", event, json.dumps(sanitized_payload, ensure_ascii=False, default=str))


def sanitize_payload(value: Any) -> Any:
    """递归脱敏日志载荷中的授权信息。"""
    if isinstance(value, dict):
        sanitized: dict[str, Any] = {}
        for key, item in value.items():
            if key.lower() in {"authorization", "token"}:
                sanitized[key] = mask_secret(str(item or ""))
            else:
                sanitized[key] = sanitize_payload(item)
        return sanitized
    if isinstance(value, list):
        return [sanitize_payload(item) for item in value]
    return value


def mask_secret(value: str) -> str:
    """将 token 等敏感值压缩成可识别但不可复用的形式。"""
    if not value:
        return ""
    if len(value) <= 16:
        return "***"
    return f"{value[:10]}...{value[-6:]}(len={len(value)})"


def debug_log_path() -> Path:
    """返回默认调试日志文件路径。"""
    return Path(__file__).resolve().parents[2] / "logs" / "ai_approval_debug.log"

from __future__ import annotations

from app.services.debug_log_service import (
    debug_log_path,
    sanitize_payload,
)


def test_sanitize_payload_masks_authorization_recursively() -> None:
    """日志脱敏应递归处理 Authorization，避免完整 token 落盘。"""
    token = "Bearer abcdefghijklmnopqrstuvwxyz1234567890"

    payload = sanitize_payload(
        {
            "headers": {"Authorization": token, "UID": "863"},
            "items": [{"token": token}],
        }
    )

    assert payload["headers"]["Authorization"] != token
    assert payload["items"][0]["token"] != token
    assert "abcdefghijklmnopqrstuvwxyz" not in payload["headers"]["Authorization"]
    assert payload["headers"]["UID"] == "863"


def test_debug_log_path_is_inside_ai_approval_project() -> None:
    """调试日志应写到 AI 审批助手项目目录下。"""
    path = debug_log_path()

    assert path.parts[-3:] == ("ai_approval_assistant", "logs", "ai_approval_debug.log")

from __future__ import annotations

from app.services.env_config_service import (
    ai_approval_project_root,
)


def test_ai_approval_project_root_points_to_package_project() -> None:
    """AI 审批助手配置根目录应指向 ai_approval_assistant。"""
    assert ai_approval_project_root().name == "ai_approval_assistant"

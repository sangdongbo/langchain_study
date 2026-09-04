"""定义不依赖数据库的系统助手及助手类型判断规则。"""

from __future__ import annotations

from typing import Literal


AssistantType = Literal["approval", "rag"]

# 审批助手由服务端固定提供，不写入 RAG Assistant 配置表。
APPROVAL_ASSISTANT_KEY = "approval-assistant"


def assistant_type_for_key(assistant_key: str) -> AssistantType:
    """仅根据服务端保留键判断助手类型，不信任客户端声明。"""
    return "approval" if assistant_key.strip() == APPROVAL_ASSISTANT_KEY else "rag"


def approval_assistant_item() -> dict[str, object]:
    """返回统一助手列表中的固定审批助手。"""
    return {
        "id": None,
        "assistant_key": APPROVAL_ASSISTANT_KEY,
        "name": "审批助手",
        "assistant_type": "approval",
        "is_system": True,
        "status": "active",
    }

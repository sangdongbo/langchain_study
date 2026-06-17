from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Literal

from app.graph.state import ApprovalState

MemoryRole = Literal["user", "assistant"]
DEFAULT_SHORT_MEMORY_TURNS = 10


def append_user_message(
    state: ApprovalState,
    content: str,
    *,
    max_turns: int | None = None,
) -> None:
    """把用户本轮输入追加到短期会话记忆。"""
    _append_memory_item(state, "user", content, max_turns=max_turns)


def append_assistant_message(
    state: ApprovalState,
    content: str,
    *,
    max_turns: int | None = None,
) -> None:
    """把助手本轮回复追加到短期会话记忆。"""
    _append_memory_item(state, "assistant", content, max_turns=max_turns)


def memory_context_text(state: ApprovalState) -> str:
    """将短期记忆格式化为可发送给普通聊天模型的上下文文本。"""
    memory = _valid_memory_items(state)
    if not memory:
        return ""
    lines = ["短期会话记忆："]
    for item in memory:
        lines.append(f"{item['role']}: {item['content']}")
    return "\n".join(lines)


def with_memory_context(state: ApprovalState, user_message: str) -> str:
    """把短期记忆和当前输入合并为普通聊天模型的输入。"""
    context = memory_context_text(state)
    if not context:
        return user_message
    return f"{context}\n\n当前用户输入：{user_message}"


def trim_memory(state: ApprovalState, *, max_turns: int | None = None) -> None:
    """按轮次上限裁剪短期记忆，避免 Redis 状态无限增大。"""
    max_items = _max_memory_items(max_turns)
    state["short_term_memory"] = _valid_memory_items(state)[-max_items:]


def short_memory_turns_from_env() -> int:
    """读取短期记忆保留轮数配置，非法值使用默认值。"""
    raw_value = os.getenv("AI_APPROVAL_SHORT_MEMORY_TURNS", "")
    if not raw_value:
        return DEFAULT_SHORT_MEMORY_TURNS
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_SHORT_MEMORY_TURNS


def _append_memory_item(
    state: ApprovalState,
    role: MemoryRole,
    content: str,
    *,
    max_turns: int | None = None,
) -> None:
    """追加一条标准化记忆，并立即裁剪到配置上限。"""
    text = content.strip()
    if not text:
        return
    memory = _valid_memory_items(state)
    memory.append(
        {
            "role": role,
            "content": text,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "status": state.get("status", "idle"),
            "approval_type": state.get("approval_type"),
            "awaiting_field": state.get("awaiting_field"),
        }
    )
    state["short_term_memory"] = memory
    trim_memory(state, max_turns=max_turns)


def _valid_memory_items(state: ApprovalState) -> list[dict[str, object]]:
    """过滤损坏或旧格式记忆，保证后续拼接和保存稳定。"""
    raw_memory = state.get("short_term_memory", [])
    if not isinstance(raw_memory, list):
        return []
    memory: list[dict[str, object]] = []
    for item in raw_memory:
        if not isinstance(item, dict):
            continue
        role = item.get("role")
        content = item.get("content")
        if role not in {"user", "assistant"}:
            continue
        if not isinstance(content, str) or not content.strip():
            continue
        memory.append(dict(item))
    return memory


def _max_memory_items(max_turns: int | None) -> int:
    """把轮数转换为消息条数；一轮包含 user 和 assistant 两条。"""
    turns = max_turns if max_turns is not None else short_memory_turns_from_env()
    return max(1, turns) * 2

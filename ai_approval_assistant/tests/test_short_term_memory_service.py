from __future__ import annotations

from app.graph.state import initial_state
from app.services.short_term_memory_service import (
    append_assistant_message,
    append_user_message,
    memory_context_text,
)


def test_short_term_memory_keeps_recent_turns_only() -> None:
    state = initial_state("S-memory", "U001")

    append_user_message(state, "第一轮用户", max_turns=2)
    append_assistant_message(state, "第一轮助手", max_turns=2)
    append_user_message(state, "第二轮用户", max_turns=2)
    append_assistant_message(state, "第二轮助手", max_turns=2)
    append_user_message(state, "第三轮用户", max_turns=2)
    append_assistant_message(state, "第三轮助手", max_turns=2)

    assert [item["content"] for item in state["short_term_memory"]] == [
        "第二轮用户",
        "第二轮助手",
        "第三轮用户",
        "第三轮助手",
    ]


def test_memory_context_text_formats_recent_messages() -> None:
    state = initial_state("S-memory", "U001")
    append_user_message(state, "我叫张三", max_turns=10)
    append_assistant_message(state, "好的，我记住了。", max_turns=10)

    context = memory_context_text(state)

    assert "user: 我叫张三" in context
    assert "assistant: 好的，我记住了。" in context

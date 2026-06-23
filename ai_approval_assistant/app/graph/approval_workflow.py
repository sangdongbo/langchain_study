from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.approval_agent import (
    already_submitted_node,
    approval_creation_agent_node,
    assignee_node,
    cancel_node,
    clarify_node,
    classify_node,
    collect_node,
    decision_review_node,
    general_chat_node,
    load_context_node,
    preview_node,
    resume_node,
    submit_node,
    validate_node,
)
from app.graph.state import ApprovalState


def create_approval_creation_workflow():
    """创建审批发起 Agent 的内部子图。"""
    builder = StateGraph(ApprovalState)
    builder.add_node("approval_creation_entry", approval_creation_agent_node)
    builder.add_node("load_context", load_context_node)
    builder.add_node("classify", classify_node)
    builder.add_node("decision_review", decision_review_node)
    builder.add_node("collect", collect_node)
    builder.add_node("validate", validate_node)
    builder.add_node("assignee", assignee_node)
    builder.add_node("preview", preview_node)
    builder.add_node("submit", submit_node)
    builder.add_node("already_submitted", already_submitted_node)
    builder.add_node("cancel", cancel_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("general_chat", general_chat_node)
    builder.add_node("resume", resume_node)
    builder.add_edge(START, "approval_creation_entry")
    builder.add_edge("approval_creation_entry", "load_context")
    builder.add_edge("load_context", "classify")
    builder.add_edge("classify", "decision_review")
    builder.add_conditional_edges(
        "decision_review",
        _route,
        {
            "collect": "collect",
            "submit": "submit",
            "cancel": "cancel",
            "clarify": "clarify",
            "review": "decision_review",
            "already_submitted": "already_submitted",
            "general_chat": "general_chat",
            "assignee": "assignee",
            "resume": "resume",
        },
    )
    builder.add_conditional_edges(
        "collect", _route, {"validate": "validate", "end": END}
    )
    builder.add_conditional_edges("validate", _route, {"assignee": "assignee", "end": END})
    builder.add_conditional_edges("assignee", _route, {"preview": "preview", "end": END})
    builder.add_edge("preview", END)
    builder.add_edge("submit", END)
    builder.add_edge("already_submitted", END)
    builder.add_edge("cancel", END)
    builder.add_edge("clarify", END)
    builder.add_edge("general_chat", END)
    builder.add_edge("resume", END)
    return builder.compile()


def _route(state: ApprovalState) -> str:
    """从状态中读取下一步图路由。"""
    return state.get("_route", "end")


__all__ = ["create_approval_creation_workflow"]

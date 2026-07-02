from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.daily_report_agentic_workflow_demo import (
    demo_agent_compose_node,
    demo_agent_plan_node,
    demo_confirm_date_node,
    demo_load_context_node,
    demo_preview_gate_node,
    demo_save_draft_node,
    demo_submit_gate_node,
)
from app.graph.state import ApprovalState


def create_daily_report_agentic_workflow_demo():
    """Create a standalone demo graph for agentic workflow daily reports."""
    builder = StateGraph(ApprovalState)
    builder.add_node("demo_agent_plan", demo_agent_plan_node)
    builder.add_node("demo_confirm_date", demo_confirm_date_node)
    builder.add_node("demo_load_context", demo_load_context_node)
    builder.add_node("demo_agent_compose", demo_agent_compose_node)
    builder.add_node("demo_save_draft", demo_save_draft_node)
    builder.add_node("demo_preview_gate", demo_preview_gate_node)
    builder.add_node("demo_submit_gate", demo_submit_gate_node)

    builder.add_edge(START, "demo_agent_plan")
    builder.add_conditional_edges(
        "demo_agent_plan",
        _route,
        {
            "confirm_date": "demo_confirm_date",
            "submit": "demo_submit_gate",
            "end": END,
        },
    )
    builder.add_edge("demo_confirm_date", "demo_load_context")
    builder.add_edge("demo_load_context", "demo_agent_compose")
    builder.add_conditional_edges(
        "demo_agent_compose",
        _route,
        {
            "save": "demo_save_draft",
            "end": END,
        },
    )
    builder.add_edge("demo_save_draft", "demo_preview_gate")
    builder.add_edge("demo_preview_gate", END)
    builder.add_edge("demo_submit_gate", END)
    return builder.compile()


def _route(state: ApprovalState) -> str:
    return state.get("_route", "end")


__all__ = ["create_daily_report_agentic_workflow_demo"]

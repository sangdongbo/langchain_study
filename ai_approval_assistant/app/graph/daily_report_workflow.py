from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agents.daily_report_chat_agent import (
    cancel_daily_report_node,
    collect_daily_report_content_node,
    collect_daily_report_date_node,
    daily_report_action_node,
    daily_report_entry_node,
    interrupt_daily_report_node,
    load_daily_report_context_node,
    preview_daily_report_node,
    save_daily_report_draft_node,
    submit_daily_report_node,
)
from app.graph.state import ApprovalState


def create_daily_report_workflow():
    """创建日报 Agent 的内部子图。"""
    import app.agents.daily_report_chat_agent as daily_report_agent
    from app.tools import daily_report_tools

    # 子图通过 tools 调用日报服务；这里同步旧模块变量，保证测试替换服务后
    # 新的 tools 路径也能使用同一个 fake service。
    daily_report_tools.daily_report_service = daily_report_agent.daily_report_service

    builder = StateGraph(ApprovalState)
    builder.add_node("daily_report_entry", daily_report_entry_node)
    builder.add_node("daily_report_action", daily_report_action_node)
    builder.add_node("load_daily_report_context", load_daily_report_context_node)
    builder.add_node("collect_daily_report_content", collect_daily_report_content_node)
    builder.add_node("collect_daily_report_date", collect_daily_report_date_node)
    builder.add_node("save_daily_report_draft", save_daily_report_draft_node)
    builder.add_node("preview_daily_report", preview_daily_report_node)
    builder.add_node("submit_daily_report", submit_daily_report_node)
    builder.add_node("cancel_daily_report", cancel_daily_report_node)
    builder.add_node("interrupt_daily_report", interrupt_daily_report_node)

    builder.add_edge(START, "daily_report_entry")
    builder.add_edge("daily_report_entry", "daily_report_action")
    builder.add_conditional_edges(
        "daily_report_action",
        _route,
        {
            # action_agent 只产出业务动作，具体节点连线统一在子图里声明，
            # 这样 Studio 能看到日报内部流程，而顶层图仍然保持干净。
            "load": "load_daily_report_context",
            "collect_content": "collect_daily_report_content",
            "collect_date": "collect_daily_report_date",
            "submit": "submit_daily_report",
            "cancel": "cancel_daily_report",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "load_daily_report_context",
        _route,
        {
            "save": "save_daily_report_draft",
            "interrupt": "interrupt_daily_report",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "collect_daily_report_content",
        _route,
        {
            "save": "save_daily_report_draft",
            "interrupt": "interrupt_daily_report",
            "end": END,
        },
    )
    builder.add_conditional_edges(
        "collect_daily_report_date",
        _route,
        {
            "load": "load_daily_report_context",
            "interrupt": "interrupt_daily_report",
            "end": END,
        },
    )
    builder.add_edge("save_daily_report_draft", "preview_daily_report")
    builder.add_conditional_edges(
        "preview_daily_report",
        _route,
        {
            "interrupt": "interrupt_daily_report",
            "end": END,
        },
    )
    builder.add_edge("interrupt_daily_report", END)
    builder.add_edge("submit_daily_report", END)
    builder.add_edge("cancel_daily_report", END)
    return builder.compile()


def _route(state: ApprovalState) -> str:
    return state.get("_route", "end")

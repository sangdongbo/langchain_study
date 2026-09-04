"""可复用的业务子图装配器。

子图只编排已有节点，不在这里实现业务规则。根图负责身份、路由和最终回答，
各子图负责一个业务边界，后续可以在子图内部增加只读 Worker 而不改变 HTTP 契约。
"""

from __future__ import annotations

from typing import Any, Callable

from langgraph.graph import END, START, StateGraph

from ai_erp_rag_assistant.app.graph.state import ErpRagState


Node = Callable[..., dict[str, Any]]


def create_rag_retrieval_subgraph(retrieve_node: Node) -> Any:
    """封装 RAG 检索阶段；回答节点留在根图以保持现有流式协议。"""
    builder = StateGraph(ErpRagState)
    builder.add_node("retrieve_rag", retrieve_node)
    builder.add_edge(START, "retrieve_rag")
    builder.add_edge("retrieve_rag", END)
    return builder.compile()


def create_erp_status_subgraph(query_node: Node) -> Any:
    """封装 ERP 审批状态读取，后续可在内部增加分页或聚合 Worker。"""
    builder = StateGraph(ErpRagState)
    builder.add_node("query_erp_status", query_node)
    builder.add_edge(START, "query_erp_status")
    builder.add_edge("query_erp_status", END)
    return builder.compile()


def create_approval_subgraph(
    load_template_node: Node,
    validate_node: Node,
    submit_node: Node,
) -> Any:
    """编排审批草稿、冻结预览和提交闸门。

    已有冻结预览的确认请求直接进入 submit，避免再次调用 Planner 或重新生成预览。
    """
    builder = StateGraph(ErpRagState)
    builder.add_node("load_approval_template", load_template_node)
    builder.add_node("validate_and_preview", validate_node)
    builder.add_node("submit_if_confirmed", submit_node)
    builder.add_conditional_edges(
        START,
        lambda state: "submit"
        if state.get("confirm") is True and state.get("preview")
        else "collect",
        {"collect": "load_approval_template", "submit": "submit_if_confirmed"},
    )
    builder.add_conditional_edges(
        "load_approval_template",
        lambda state: "validate",
        {"validate": "validate_and_preview"},
    )
    # 只有显式确认且仍有预览快照时才允许进入提交节点。
    builder.add_conditional_edges(
        "validate_and_preview",
        lambda state: "submit"
        if state.get("confirm") is True and state.get("preview")
        else "end",
        {"submit": "submit_if_confirmed", "end": END},
    )
    builder.add_edge("submit_if_confirmed", END)
    return builder.compile()

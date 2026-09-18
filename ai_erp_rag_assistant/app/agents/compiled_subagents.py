"""把确定性的业务子图封装成 DeepAgent ``CompiledSubAgent``。

该模块只增加子代理协议，不复制业务规则。HTTP 接口可通过编排器配置在原根图和
DeepAgent Harness 之间切换，两种入口复用相同的三个受限领域子图。
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any, NotRequired

from deepagents import CompiledSubAgent
from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.runnables import RunnableConfig
from langgraph.graph import END, START, MessagesState, StateGraph

from ai_erp_rag_assistant.app.graph.subgraphs import (
    create_approval_subgraph,
    create_erp_status_subgraph,
    create_rag_retrieval_subgraph,
)
from ai_erp_rag_assistant.app.services.model_service import model_service


Node = Callable[..., dict[str, Any]]


class RagCompiledState(MessagesState, total=False):
    """RAG 子代理内部状态；只包含检索所需输入和结果。"""

    query: str
    user_message: str
    assistant_key: str
    user_context: dict[str, Any]
    plan: dict[str, Any]
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    retrieval_status: str
    route: str
    tool_calls: list[dict[str, Any]]
    structured_response: NotRequired[dict[str, Any]]


class ApprovalCompiledState(MessagesState, total=False):
    """审批子代理内部状态；保留冻结预览流程所需字段。"""

    user_message: str
    user_id: str
    uid: str
    user_context: dict[str, Any]
    plan: dict[str, Any]
    conversation: list[dict[str, str]]
    selected_template_id: str
    template: dict[str, Any]
    template_candidates: list[dict[str, Any]]
    template_selection_required: bool
    fields: dict[str, Any]
    form_schema: dict[str, Any]
    selected_assignees: dict[str, list[str]]
    draft_key: str
    consumed_preview: dict[str, Any]
    preview: dict[str, Any]
    confirm: bool | None
    confirm_preview_id: str
    confirm_preview_version: int | None
    confirm_preview_hash: str
    workflow_status: str
    active_approval: bool
    pending_question: str
    assistant_message: str
    erp_data: dict[str, Any]
    tool_calls: list[dict[str, Any]]
    errors: list[str]
    route: str
    structured_response: NotRequired[dict[str, Any]]


class ErpStatusCompiledState(MessagesState, total=False):
    """ERP 状态子代理内部状态。"""

    user_id: str
    user_context: dict[str, Any]
    erp_data: dict[str, Any]
    workflow_status: str
    tool_calls: list[dict[str, Any]]
    route: str
    structured_response: NotRequired[dict[str, Any]]


def _domain_runner(
    domain_graph: Any,
    *,
    task_message_as_query: bool = False,
) -> Node:
    """创建调用现有业务子图的节点，并剔除 DeepAgent 专用输出字段。"""

    def run(state: Mapping[str, Any], config: RunnableConfig) -> dict[str, Any]:
        domain_input = {
            key: value
            for key, value in state.items()
            if key not in {"messages", "structured_response"}
        }
        if task_message_as_query:
            # DeepAgents 会把父 Agent 的 task.description 作为唯一 HumanMessage
            # 交给隔离子代理；它包含结合历史改写后的完整问题。该值只影响检索词，
            # 公司、部门和权限仍由服务端 user_context 决定。
            delegated_query = next(
                (
                    str(message.content).strip()[:10_000]
                    for message in reversed(list(state.get("messages", [])))
                    if isinstance(message, HumanMessage)
                    and isinstance(message.content, str)
                    and message.content.strip()
                ),
                "",
            )
            if delegated_query:
                domain_input["query"] = delegated_query
        return dict(domain_graph.invoke(domain_input, config=config))

    return run


def _bounded_evidence(evidence: Sequence[Mapping[str, Any]]) -> list[dict[str, Any]]:
    """压缩检索结果，防止父 Agent 上下文被完整 Chunk 撑大。"""
    allowed = (
        "chunk_id",
        "source",
        "title",
        "page",
        "version",
        "knowledge_base_key",
        "knowledge_base_name",
        "score",
        "rerank_score",
    )
    return [
        {
            **{
                key: item.get(key)
                for key in allowed
                if item.get(key) not in (None, "")
            },
            "text": str(item.get("text") or "")[:1200],
        }
        for item in evidence[:10]
    ]


def _finish_rag(state: RagCompiledState) -> dict[str, Any]:
    evidence = list(state.get("evidence", []))
    response = {
        "status": "completed",
        "result_count": len(evidence),
        "evidence": _bounded_evidence(evidence),
        "citations": model_service.build_citations(evidence),
    }
    return {
        "messages": [AIMessage(content=f"RAG 检索完成，共返回 {len(evidence)} 条证据。")],
        "route": "knowledge",
        "structured_response": response,
    }


def _finish_erp_status(state: ErpStatusCompiledState) -> dict[str, Any]:
    data = dict(state.get("erp_data", {}))
    return {
        "messages": [AIMessage(content="ERP 审批状态查询完成。")],
        "route": "erp_status",
        "structured_response": {"status": "completed", "erp_data": data},
    }


def _finish_approval(state: ApprovalCompiledState) -> dict[str, Any]:
    workflow_status = str(state.get("workflow_status") or "idle")
    message = str(
        state.get("assistant_message")
        or state.get("pending_question")
        or "审批流程已处理。"
    )
    # 仅返回前端继续交互需要的业务字段，不返回 user_context、Token 或完整会话状态。
    response = {
        "status": workflow_status,
        "message": message,
        "pending_question": str(state.get("pending_question") or ""),
        "template_selection_required": bool(
            state.get("template_candidates") and not state.get("template")
        ),
        "template_candidates": list(state.get("template_candidates", [])),
        "form_schema": dict(state.get("form_schema", {})),
        "preview": dict(state.get("preview", {})),
        "erp_data": dict(state.get("erp_data", {})),
        "errors": list(state.get("errors", [])),
    }
    return {
        "messages": [AIMessage(content=message)],
        "route": "approval_workflow",
        "structured_response": response,
    }


def _wrap_domain_graph(
    state_schema: type,
    domain_graph: Any,
    finish_node: Node,
    *,
    task_message_as_query: bool = False,
) -> Any:
    """为现有业务子图补充 CompiledSubAgent 所需的消息和结构化输出。"""
    builder = StateGraph(state_schema)
    builder.add_node(
        "run_domain_graph",
        _domain_runner(
            domain_graph,
            task_message_as_query=task_message_as_query,
        ),
    )
    builder.add_node("build_subagent_result", finish_node)
    builder.add_edge(START, "run_domain_graph")
    builder.add_edge("run_domain_graph", "build_subagent_result")
    builder.add_edge("build_subagent_result", END)
    return builder.compile()


def create_domain_compiled_subagents(
    *,
    rag_retrieve_node: Node,
    erp_status_node: Node,
    approval_load_node: Node,
    approval_validate_node: Node,
    approval_submit_node: Node,
) -> list[CompiledSubAgent]:
    """基于现有确定性节点创建 RAG、ERP 状态和审批子代理。"""
    rag_graph = create_rag_retrieval_subgraph(rag_retrieve_node)
    erp_status_graph = create_erp_status_subgraph(erp_status_node)
    approval_graph = create_approval_subgraph(
        approval_load_node,
        approval_validate_node,
        approval_submit_node,
    )
    return [
        {
            "name": "rag-retrieval",
            "description": "检索当前租户允许访问的企业知识库并返回带来源的证据。",
            "runnable": _wrap_domain_graph(
                RagCompiledState,
                rag_graph,
                _finish_rag,
                task_message_as_query=True,
            ),
        },
        {
            "name": "erp-status",
            "description": "查询当前已验证用户的 ERP 审批状态，只执行只读操作。",
            "runnable": _wrap_domain_graph(
                ErpStatusCompiledState,
                erp_status_graph,
                _finish_erp_status,
            ),
        },
        {
            "name": "approval-workflow",
            "description": "处理审批模板、字段校验、冻结预览和确认后的幂等提交。",
            "runnable": _wrap_domain_graph(
                ApprovalCompiledState,
                approval_graph,
                _finish_approval,
            ),
        },
    ]

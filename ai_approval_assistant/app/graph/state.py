from __future__ import annotations
from typing import Any, TypedDict

from langgraph.prebuilt.chat_agent_executor import AgentState


class ApprovalAgentState(AgentState, total=False):
    """审批多 Agent 共享状态。

    继承 LangGraph 的 AgentState 后，审批 Agent、用户信息 Agent 等后续子图
    可以通过 messages/remaining_steps 与审批业务字段在同一个状态对象中通信。
    """

    session_id: str
    user_id: str
    uid: str | None
    authorization: str | None
    user_message: str
    status: str
    intent: str | None
    approval_type: str | None
    collected_slots: dict[str, str]
    collected_values: dict[str, Any]
    awaiting_field: str | None
    preview: dict[str, Any] | None
    confirmed: bool
    request_id: str | None
    approval_node: str | None
    approval_nodes: list[dict[str, Any]]
    selected_assignees: dict[str, list[str]]
    assistant_message: str
    errors: list[str]
    field_errors: list[dict[str, Any]]
    idempotency_key: str | None
    trace: list[str]
    review_count: int
    _route: str
    _user_context: dict[str, Any] | None
    _available_templates: list[dict[str, Any]]
    _template_candidates: list[dict[str, Any]]
    _template_search_keyword: str
    _current_template: dict[str, Any] | None
    _answer: dict[str, Any] | None
    _validation_warnings: list[str]
    _field_labels: dict[str, str]


ApprovalState = ApprovalAgentState


def initial_state(session_id: str, user_id: str) -> ApprovalState:
    """为新聊天会话创建初始内存状态。"""
    return {
        "messages": [],
        "remaining_steps": 20,
        "session_id": session_id,
        "user_id": user_id,
        "uid": None,
        "authorization": None,
        "user_message": "",
        "status": "idle",
        "intent": None,
        "approval_type": None,
        "collected_slots": {},
        "collected_values": {},
        "awaiting_field": None,
        "preview": None,
        "confirmed": False,
        "request_id": None,
        "approval_node": None,
        "approval_nodes": [],
        "selected_assignees": {},
        "assistant_message": "",
        "errors": [],
        "field_errors": [],
        "idempotency_key": None,
        "trace": [],
        "review_count": 0,
        "_route": "end",
        "_user_context": None,
        "_available_templates": [],
        "_template_candidates": [],
        "_template_search_keyword": "",
        "_current_template": None,
        "_answer": None,
        "_validation_warnings": [],
        "_field_labels": {},
    }

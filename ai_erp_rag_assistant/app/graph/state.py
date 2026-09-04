"""LangGraph ERP/RAG 工作流共享状态及跨轮恢复规则。"""

from __future__ import annotations

from typing import Any, TypedDict


class ErpRagState(TypedDict, total=False):
    """一次会话中路由、检索、审批草稿和审计信息的统一状态。"""

    session_id: str
    assistant_type: str
    user_id: str
    user_message: str
    uid: str
    authorization: str
    company_id: str
    department: str
    confirm: bool | None
    route: str
    plan: dict[str, Any]
    user_context: dict[str, Any]
    template: dict[str, Any]
    template_candidates: list[dict[str, Any]]
    conversation: list[dict[str, str]]
    fields: dict[str, Any]
    form_schema: dict[str, Any]
    selected_assignees: dict[str, list[str]]
    draft_key: str
    consumed_preview: dict[str, Any]
    evidence: list[dict[str, Any]]
    erp_data: dict[str, Any]
    preview: dict[str, Any]
    workflow_status: str
    confirm_preview_id: str
    confirm_preview_version: int | None
    confirm_preview_hash: str
    active_approval: bool
    tool_calls: list[dict[str, Any]]
    errors: list[str]
    pending_question: str
    assistant_message: str


def initial_state(
    session_id: str,
    user_id: str,
    message: str,
    *,
    assistant_type: str = "",
    uid: str = "",
    authorization: str = "",
    company_id: str = "",
    department: str = "",
    confirm: bool | None = None,
    confirm_preview_id: str = "",
    confirm_preview_version: int | None = None,
    confirm_preview_hash: str = "",
    form_values: dict[str, Any] | None = None,
    selected_assignees: dict[str, list[str]] | None = None,
    prior: ErpRagState | None = None,
) -> ErpRagState:
    """合并上一轮安全状态与本轮输入，并重置本轮临时输出。"""
    prior = prior or {}
    prior_active_approval = bool(prior.get("active_approval", False))
    return {
        "session_id": session_id,
        "assistant_type": assistant_type or str(prior.get("assistant_type", "")),
        "user_id": user_id,
        "user_message": message,
        "uid": uid or prior.get("uid", ""),
        "authorization": authorization or prior.get("authorization", ""),
        "company_id": company_id or prior.get("company_id", ""),
        "department": department or prior.get("department", ""),
        "confirm": confirm,
        "confirm_preview_id": confirm_preview_id,
        "confirm_preview_version": confirm_preview_version,
        "confirm_preview_hash": confirm_preview_hash,
        "route": "unknown",
        "plan": dict(prior.get("plan", {})),
        "user_context": {},
        "template": dict(prior.get("template", {})),
        "template_candidates": list(prior.get("template_candidates", [])),
        "conversation": [
            *list(prior.get("conversation", [])),
            *([{"role": "assistant", "content": str(prior["pending_question"])}] if prior.get("pending_question") else []),
            {"role": "user", "content": message},
        ][-16:],
        "fields": {**dict(prior.get("fields", {})), **dict(form_values or {})},
        "form_schema": dict(prior.get("form_schema", {})),
        "selected_assignees": {
            **dict(prior.get("selected_assignees", {})),
            **dict(selected_assignees or {}),
        },
        "draft_key": str(prior.get("draft_key", "")),
        "consumed_preview": {},
        "evidence": [],
        "erp_data": {},
        # 已关闭的预览可以在当前响应中返回一次供展示，但下一轮不能重新变成可操作草稿。
        "preview": dict(prior.get("preview", {})) if prior_active_approval else {},
        "workflow_status": str(
            (
                prior.get("workflow_status")
                or ("preview_ready" if prior.get("preview") else "collecting_fields")
            )
            if prior_active_approval
            else "idle"
        ),
        "active_approval": prior_active_approval,
        "tool_calls": [],
        "errors": [],
        "pending_question": str(prior.get("pending_question", "")),
        "assistant_message": "",
    }

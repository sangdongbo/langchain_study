"""LangGraph ERP/RAG 工作流共享状态及跨轮恢复规则。"""

from __future__ import annotations

from typing import Any, TypedDict


class RagState(TypedDict, total=False):
    """RAG 子代理使用的最小状态。

    该类型只描述检索边界和检索结果，不把完整 ERP 审批草稿暴露给 RAG 工具。
    ``user_context`` 必须由服务端完成身份校验后写入，工具不会采信状态外层伪造的
    ``permission_tags``、公司或部门字段。
    """

    query: str
    assistant_key: str
    company_id: str
    department: str
    permission_tags: list[str]
    user_context: dict[str, Any]
    retrieval_scope: dict[str, Any]
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    retrieval_status: str


class ApprovalState(TypedDict, total=False):
    """审批子代理使用的最小状态。

    提交工具只读取 ``preview`` 冻结快照和服务端注入的 ``user_context``，不接受
    模型通过工具参数覆盖租户、用户或认证信息。
    """

    user_message: str
    user_id: str
    company_id: str
    department: str
    user_context: dict[str, Any]
    selected_template_id: str
    template: dict[str, Any]
    template_candidates: list[dict[str, Any]]
    fields: dict[str, Any]
    form_schema: dict[str, Any]
    preview: dict[str, Any]
    confirm: bool | None
    confirm_preview_id: str
    confirm_preview_version: int | None
    confirm_preview_hash: str
    workflow_status: str


class ErpStatusState(TypedDict, total=False):
    """ERP 状态查询子代理使用的最小状态。"""

    user_id: str
    company_id: str
    department: str
    user_context: dict[str, Any]
    erp_data: dict[str, Any]
    workflow_status: str


class ErpRagState(TypedDict, total=False):
    """一次会话中路由、检索、审批草稿和审计信息的统一状态。"""

    session_id: str
    assistant_type: str
    # thread_id 表示会话，execution_run_id 表示当前一次可恢复的 ERP 执行。
    execution_run_id: str
    execution_status: str
    execution_retry_count: int
    execution_current_step: str
    selected_template_id: str
    user_id: str
    user_message: str
    # query 是本轮检索专用问题，可由 Planner 或 DeepAgent task 改写；不能跨轮继承。
    query: str
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
    template_selection_required: bool
    conversation: list[dict[str, str]]
    fields: dict[str, Any]
    form_schema: dict[str, Any]
    selected_assignees: dict[str, list[str]]
    invalid_assignee_nodes: list[dict[str, str]]
    draft_key: str
    consumed_preview: dict[str, Any]
    evidence: list[dict[str, Any]]
    citations: list[dict[str, Any]]
    retrieval_status: str
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
    selected_template_id: str = "",
    form_values: dict[str, Any] | None = None,
    selected_assignees: dict[str, list[str]] | None = None,
    prior: ErpRagState | None = None,
) -> ErpRagState:
    """合并上一轮安全状态与本轮输入，并重置本轮临时输出。"""
    prior = prior or {}
    prior_active_approval = bool(prior.get("active_approval", False))
    conversation = list(prior.get("conversation", []))
    pending_question = str(prior.get("pending_question", ""))
    # DeepAgent 已把最终审批提示写入 conversation 时不能重复追加；旧状态没有
    # 保存助手轮次时仍兼容 pending_question 的历史恢复方式。
    if pending_question and not (
        conversation
        and conversation[-1].get("role") == "assistant"
        and str(conversation[-1].get("content") or "") == pending_question
    ):
        conversation.append({"role": "assistant", "content": pending_question})
    conversation.append({"role": "user", "content": message})
    return {
        "session_id": session_id,
        "assistant_type": assistant_type or str(prior.get("assistant_type", "")),
        "execution_run_id": str(prior.get("execution_run_id", "")),
        "execution_status": str(prior.get("execution_status", "")),
        "execution_retry_count": int(prior.get("execution_retry_count", 0) or 0),
        "execution_current_step": str(prior.get("execution_current_step", "")),
        # 只保留本轮明确选择；模板成功加载后不再依赖这个临时值。
        "selected_template_id": str(selected_template_id or "").strip(),
        "user_id": user_id,
        "user_message": message,
        "query": "",
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
        "template_selection_required": bool(prior.get("template_selection_required", False)),
        "conversation": conversation[-16:],
        "fields": {**dict(prior.get("fields", {})), **dict(form_values or {})},
        "form_schema": dict(prior.get("form_schema", {})),
        "selected_assignees": {
            **dict(prior.get("selected_assignees", {})),
            **dict(selected_assignees or {}),
        },
        "draft_key": str(prior.get("draft_key", "")),
        "consumed_preview": {},
        "evidence": [],
        "citations": [],
        "retrieval_status": "idle",
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
        "pending_question": pending_question,
        "assistant_message": "",
    }

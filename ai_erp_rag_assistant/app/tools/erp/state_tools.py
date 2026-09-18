"""基于领域 State 的 ERP 工具适配层。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ai_erp_rag_assistant.app.graph.state import ApprovalState, ErpRagState, ErpStatusState
from ai_erp_rag_assistant.app.tools.erp_tools import (
    get_approval_field_options,
    get_current_user,
    query_approval_status,
)


def get_current_user_from_state(
    state: ApprovalState | ErpStatusState | ErpRagState,
) -> dict[str, Any]:
    """读取 State 中的已验证身份，或执行一次身份校验填充上下文。"""
    existing = state.get("user_context")
    if isinstance(existing, Mapping) and str(existing.get("company_id") or "").strip():
        return dict(existing)
    user_id = str(state.get("user_id") or state.get("uid") or "").strip()
    if not user_id:
        raise ValueError("ERP State 缺少 user_id")
    return get_current_user(
        user_id,
        uid=str(state.get("uid") or "").strip(),
        authorization=str(state.get("authorization") or "").strip(),
        company_id=str(state.get("company_id") or "").strip(),
        department=str(state.get("department") or "").strip(),
    )


def query_approval_status_from_state(
    state: ErpStatusState | ErpRagState,
    *,
    query_fn: Callable[..., dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """按已验证用户读取 ERP 审批状态。"""
    user = get_current_user_from_state(state)
    user_id = str(user.get("uid") or user.get("user_id") or state.get("user_id") or "").strip()
    if not user_id:
        raise PermissionError("当前用户没有可用的用户ID")
    # query_fn 只服务于旧工作流兼容注入，不开放给模型决定调用目标。
    query = query_fn or query_approval_status
    return query(user_id, user=user)


def get_approval_field_options_from_state(
    state: ApprovalState | ErpRagState,
    *,
    field_key: str,
    keyword: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    """按 State 中已选模板查询动态字段候选项。"""
    user = get_current_user_from_state(state)
    template = state.get("template")
    template_id = ""
    title = ""
    if isinstance(template, Mapping):
        template_id = str(template.get("template_id") or "").strip()
        title = str(template.get("title") or "").strip()
    template_id = template_id or str(state.get("selected_template_id") or "").strip()
    if not template_id:
        raise ValueError("ERP State 缺少 selected_template_id")
    return get_approval_field_options(
        template_id,
        field_key,
        str(user["company_id"]).strip(),
        title=title,
        keyword=keyword,
        page=page,
        page_size=page_size,
        user=user,
    )

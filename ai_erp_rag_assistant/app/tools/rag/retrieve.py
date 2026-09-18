"""基于领域 State 的 RAG 检索工具适配层。"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from typing import Any

from ai_erp_rag_assistant.app.graph.state import ErpRagState, RagState
from ai_erp_rag_assistant.app.rag_admin_repository import RagRuntimeConfig
from ai_erp_rag_assistant.app.tools.rag_tools import search_knowledge
from ai_erp_rag_assistant.app.tools.state_context import (
    verified_permission_tags,
    verified_user_context,
)


def _state_query(state: Mapping[str, Any], query: str) -> str:
    """按领域 State 的稳定优先级取得检索问题。"""
    explicit = str(query or "").strip()
    if explicit:
        return explicit
    plan = state.get("plan")
    if isinstance(plan, Mapping):
        planned_query = str(plan.get("query") or "").strip()
        if planned_query:
            return planned_query
    for key in ("query", "user_message"):
        value = str(state.get(key) or "").strip()
        if value:
            return value
    raise ValueError("RAG State 缺少 query")


def retrieve_from_state(
    state: RagState | ErpRagState,
    *,
    runtime: RagRuntimeConfig | None = None,
    query: str = "",
    search_fn: Callable[..., list[dict[str, Any]]] | None = None,
) -> list[dict[str, Any]]:
    """从服务端验证过的 State 执行一次知识检索。

    ``runtime`` 由 API/编排层从已发布 Assistant 配置生成，不能由模型工具参数
    自行构造。公司、部门和权限始终取自 ERP 校验后的 ``user_context``，而不是
    State 中可能来自请求体的同名字段。
    """
    user = verified_user_context(state)
    actual_query = _state_query(state, query)
    top_k = runtime.top_k if runtime and runtime.top_k is not None else 5
    # search_fn 仅用于工作流兼容注入和单元测试，不属于 LLM 可见的工具参数。
    search = search_fn or search_knowledge
    return search(
        actual_query,
        company_id=str(user["company_id"]).strip(),
        department=str(user.get("department") or "").strip(),
        permission_tags=verified_permission_tags(user),
        top_k=top_k,
        runtime=runtime,
    )

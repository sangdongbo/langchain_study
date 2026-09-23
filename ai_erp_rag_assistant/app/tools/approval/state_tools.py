"""基于领域 State 的审批工具适配层。"""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from typing import Any

from ai_erp_rag_assistant.app.graph.state import ApprovalState, ErpRagState
from ai_erp_rag_assistant.app.services.approval_form_service import validate_approval_fields
from ai_erp_rag_assistant.app.tools.erp_tools import (
    get_approval_template,
    list_approval_templates,
    submit_approval,
)
from ai_erp_rag_assistant.app.tools.state_context import verified_user_context


def _approval_query(state: Mapping[str, Any]) -> str:
    """按 State 中的审批意图生成模板目录查询词。"""
    plan = state.get("plan")
    if isinstance(plan, Mapping) and str(plan.get("approval_type") or "").strip():
        return str(plan["approval_type"]).strip()
    template = state.get("template")
    if isinstance(template, Mapping) and str(template.get("title") or "").strip():
        return str(template["title"]).strip()
    return str(state.get("user_message") or "").strip()


def load_template_from_state(
    state: ApprovalState | ErpRagState,
) -> dict[str, Any]:
    """读取当前用户可见的审批模板，并在多候选时返回选择信息。

    模板 ID 只从 State 的 ``selected_template_id`` 读取；调用方不能通过额外参数
    绕过 ERP 返回的候选模板归属校验。
    """
    user = verified_user_context(state)
    company_id = str(user["company_id"]).strip()
    selected_id = str(state.get("selected_template_id") or "").strip()
    query = _approval_query(state)
    candidates = list_approval_templates(
        "" if selected_id else query,
        company_id,
        user=user,
    )
    if not candidates:
        return {"template": {}, "candidates": [], "selection_required": False}
    selected = next(
        (item for item in candidates if str(item.get("template_id") or "") == selected_id),
        None,
    ) if selected_id else (candidates[0] if len(candidates) == 1 else None)
    if selected is None:
        return {
            "template": {},
            "candidates": candidates,
            "selection_required": True,
        }
    template_id = str(selected.get("template_id") or "").strip()
    if not template_id:
        raise RuntimeError("ERP 返回的审批模板缺少 template_id")
    template = get_approval_template(
        template_id,
        company_id,
        title=str(selected.get("title") or ""),
        user=user,
    )
    return {
        "template": template,
        "candidates": candidates,
        "selection_required": False,
    }


def validate_fields_from_state(
    state: ApprovalState | ErpRagState,
) -> dict[str, Any]:
    """校验 State 中当前模板和字段，并返回结构化结果。

    校验逻辑属于审批领域服务，Graph 和 Tool 共用同一个实现。
    """
    template = state.get("template")
    if not isinstance(template, Mapping) or not template:
        raise ValueError("Approval State 缺少 template")
    fields = state.get("fields")
    if not isinstance(fields, Mapping):
        fields = {}
    missing, invalid = validate_approval_fields(dict(template), dict(fields))
    return {
        "valid": not missing and not invalid,
        "missing": missing,
        "invalid": invalid,
    }


def build_preview_from_state(
    state: ApprovalState | ErpRagState,
) -> dict[str, Any]:
    """返回 State 中已冻结的审批预览副本。

    第一阶段不重新拼装预览，防止工具绕过现有字段、审批人和哈希校验；真正的
    预览生成仍由确定性的审批节点完成。
    """
    preview = state.get("preview")
    if not isinstance(preview, Mapping) or not preview:
        raise ValueError("Approval State 缺少可提交的 preview")
    if not preview.get("preview_id") or not preview.get("preview_hash"):
        raise ValueError("审批预览缺少冻结标识")
    return deepcopy(dict(preview))


def submit_confirmed_preview_from_state(
    state: ApprovalState | ErpRagState,
) -> dict[str, Any]:
    """只提交用户确认且标识完整匹配的 State 冻结预览。"""
    if state.get("confirm") is not True:
        raise ValueError("审批预览尚未收到用户确认")
    user = verified_user_context(state)
    preview = build_preview_from_state(state)
    if preview.get("requires_confirmation") is False:
        raise ValueError("当前审批预览不满足提交条件")
    checks = (
        (state.get("confirm_preview_id"), preview.get("preview_id"), "预览标识"),
        (state.get("confirm_preview_version"), preview.get("preview_version"), "预览版本"),
        (state.get("confirm_preview_hash"), preview.get("preview_hash"), "预览内容"),
    )
    for requested, current, label in checks:
        if requested not in (None, "") and str(requested) != str(current):
            raise ValueError(f"{label}已变化，请重新确认最新审批预览")
    if not preview.get("idempotency_key"):
        raise ValueError("审批预览缺少幂等键")
    return submit_approval(preview, user=user)

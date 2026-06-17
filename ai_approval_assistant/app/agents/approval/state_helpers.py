from __future__ import annotations

from typing import Any

from app.graph.state import ApprovalState
from app.schemas.approval import ApprovalNode, ApprovalTemplate, UserContext


def templates_from_state(state: ApprovalState) -> list[ApprovalTemplate]:
    """从图状态中反序列化可用模板。"""
    return [ApprovalTemplate(**item) for item in state.get("_available_templates", [])]


def template_candidates_from_state(state: ApprovalState) -> list[ApprovalTemplate]:
    """从图状态中反序列化等待用户选择的候选模板。"""
    return [ApprovalTemplate(**item) for item in state.get("_template_candidates", [])]


def nodes_from_state(state: ApprovalState) -> list[ApprovalNode]:
    """从状态中反序列化审批节点。"""
    return [ApprovalNode(**item) for item in state.get("approval_nodes", [])]


def user_from_state(state: ApprovalState, crm_approval_service) -> UserContext:
    """从图状态中反序列化或重建用户上下文。"""
    user_data = state.get("_user_context")
    if not user_data:
        return crm_approval_service.get_user_context(
            state["user_id"],
            uid=state.get("uid"),
            authorization=state.get("authorization"),
        )
    return UserContext(**user_data)


def template_detail_for_state(
    state: ApprovalState,
    approval_type: str,
    user: UserContext,
    crm_approval_service,
) -> ApprovalTemplate:
    """返回当前模板详情，优先复用本轮或会话缓存，减少远程重复请求。"""
    cached = state.get("_current_template")
    if isinstance(cached, dict) and cached.get("approval_type") == approval_type:
        return ApprovalTemplate(**cached)
    template = crm_approval_service.get_template_detail(approval_type, user)
    state["_current_template"] = template.model_dump()
    return template


def form_value_from_slots(slots: dict[str, str]) -> list[dict[str, str]]:
    """将已收集字段转换为 getNodes 需要的 form_value。"""
    return [{"field_key": key, "value": value} for key, value in slots.items()]


def submission_slots(state: ApprovalState) -> dict[str, object]:
    """合并展示字段和结构化字段，供 ERP 提交使用。"""
    slots: dict[str, object] = dict(state.get("collected_slots", {}))
    for key, value in state.get("collected_values", {}).items():
        slots[key] = value
    return slots


def slots_from_structured_answer(
    answer: dict[str, object] | None,
    awaiting_field: str | None,
    collected_slots: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, object]]:
    """将前端结构化控件答案转换为展示值和提交值。"""
    if not isinstance(answer, dict):
        return {}, {}
    field_key = str(answer.get("field_key") or "").strip()
    can_modify_collected = bool(collected_slots and field_key in collected_slots)
    if not field_key or (field_key != awaiting_field and not can_modify_collected):
        return {}, {}
    label = str(answer.get("label") or answer.get("value") or "").strip()
    if not label:
        return {}, {}
    return {
        field_key: label,
    }, {
        field_key: {
            "label": label,
            "value": answer.get("value"),
        }
    }


def clear_dependent_fields(
    slots: dict[str, str],
    collected_values: dict[str, object],
    changed_fields: Any,
    field_dependencies: dict[str, list[str]],
) -> None:
    """字段被修改后清掉依赖字段，避免预览/提交旧值。"""
    pending = list(changed_fields)
    seen: set[str] = set()
    while pending:
        field = pending.pop()
        if field in seen:
            continue
        seen.add(field)
        for dependent in field_dependencies.get(field, []):
            slots.pop(dependent, None)
            collected_values.pop(dependent, None)
            pending.append(dependent)

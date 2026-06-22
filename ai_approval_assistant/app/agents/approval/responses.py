from __future__ import annotations

from app.agents.approval.inputs import awaiting_input_for_state
from app.agents.approval.state_helpers import user_from_state
from app.graph.state import ApprovalState
from app.schemas.approval import ApprovalTemplate
from app.schemas.chat import ApprovalPreview, ChatResponse, PreviewField


def to_chat_response(state: ApprovalState, crm_approval_service) -> ChatResponse:
    """将 LangGraph 状态转换为 chat 接口的稳定响应结构。"""
    preview_data = state.get("preview")
    preview = ApprovalPreview(**preview_data) if preview_data else None

    missing_fields: list[str] = []
    if state.get("awaiting_field"):
        missing_fields.append(state["awaiting_field"])

    field_labels = field_labels_for_state(state, missing_fields, crm_approval_service)
    display_missing_fields = [
        field_labels.get(field, field) for field in missing_fields
    ]
    awaiting_field_key = state.get("awaiting_field")
    awaiting_field_label = field_labels.get(awaiting_field_key or "")

    return ChatResponse(
        session_id=state["session_id"],
        status=state.get("status", "idle"),
        assistant_message=state.get("assistant_message", ""),
        approval_type=state.get("approval_type"),
        collected_slots=state.get("collected_slots", {}),
        collected_values=state.get("collected_values", {}),
        missing_fields=display_missing_fields,
        missing_field_keys=missing_fields,
        missing_field_labels=display_missing_fields,
        awaiting_field=awaiting_field_label or awaiting_field_key,
        awaiting_field_key=awaiting_field_key,
        awaiting_field_label=awaiting_field_label,
        awaiting_input=awaiting_input_for_state(state, crm_approval_service),
        preview=preview,
        actions=actions_for_status(state.get("status", "idle")),
        request_id=state.get("request_id"),
        approval_node=state.get("approval_node"),
        field_errors=state.get("field_errors", []),
        idempotency_key=state.get("idempotency_key"),
        trace=state.get("trace", []),
        ui_action=state.get("ui_action"),
        daily_report_payload=state.get("daily_report_payload"),
        daily_report_preview=state.get("daily_report_preview"),
    )


def field_labels_for_state(
    state: ApprovalState,
    field_names: list[str],
    crm_approval_service,
) -> dict[str, str]:
    """按当前审批模板把字段 key 转成人能读懂的字段名称。"""
    if not field_names or not state.get("approval_type"):
        return {}

    labels = dict(state.get("_field_labels", {}))
    if all(field in labels for field in field_names):
        return labels

    try:
        template = crm_approval_service.get_template_detail(
            state["approval_type"], user_from_state(state, crm_approval_service)
        )
    except Exception:
        return labels

    labels.update(labels_from_template(template))
    return labels


def labels_from_template(template: ApprovalTemplate) -> dict[str, str]:
    """从模板字段中抽取字段 key 到展示名称的映射。"""
    return {field.name: field.label for field in template.fields}


def actions_for_status(status: str) -> list[str]:
    """根据审批状态返回前端可展示的动作集合。"""
    if status in {"collecting", "awaiting_assignee_selection"}:
        return ["reply", "cancel"]
    if status == "awaiting_confirmation":
        return ["confirm", "modify", "cancel"]
    if status == "awaiting_daily_report_form":
        return ["fill_form", "cancel"]
    if status == "awaiting_daily_report_confirmation":
        return ["confirm", "modify", "modify_date", "cancel"]
    if status == "submitted":
        return ["query_status"]
    if status == "daily_report_submitted":
        return ["query_status"]
    return ["reply"]


def build_preview(
    template: ApprovalTemplate,
    slots: dict[str, str],
    approval_node: str | None,
    warnings: list[str],
) -> ApprovalPreview:
    """构建审批预览模型，供确认提交前展示。"""
    return ApprovalPreview(
        approval_type=template.approval_type,
        title=template.title,
        fields=[
            PreviewField(
                name=field.name, label=field.label, value=slots.get(field.name, "")
            )
            for field in template.fields
        ],
        approval_node=approval_node,
        warnings=warnings,
    )

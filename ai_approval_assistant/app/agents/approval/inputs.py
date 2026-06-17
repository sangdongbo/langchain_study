from __future__ import annotations

from app.agents.approval.assignee import (
    assignee_selection_input,
    awaiting_assignee_node_id,
)
from app.agents.approval.state_helpers import (
    nodes_from_state,
    template_candidates_from_state,
    template_detail_for_state,
    user_from_state,
)
from app.graph.state import ApprovalState
from app.schemas.approval import ApprovalTemplate
from app.schemas.chat import AwaitingInput


def awaiting_input_for_state(
    state: ApprovalState,
    crm_approval_service,
) -> AwaitingInput | None:
    """根据审批状态构建前端可渲染的当前等待控件。"""
    if state.get("_template_candidates") and not state.get("approval_type"):
        return template_choice_input(template_candidates_from_state(state))

    awaiting_field = state.get("awaiting_field")
    if state.get("status") == "awaiting_assignee_selection":
        node_id = awaiting_assignee_node_id(awaiting_field)
        nodes = nodes_from_state(state)
        current_node = next((node for node in nodes if node.node_id == node_id), None)
        if current_node:
            return assignee_selection_input(current_node)
        return None

    if not awaiting_field or not state.get("approval_type"):
        return None

    try:
        template = template_detail_for_state(
            state,
            state["approval_type"],
            user_from_state(state, crm_approval_service),
            crm_approval_service,
        )
    except Exception:
        return None

    field = next((item for item in template.fields if item.name == awaiting_field), None)
    if not field:
        return None

    if field.type == "enum":
        return enum_input_for_field(field)

    input_type = awaiting_input_type_for_field(field)
    return AwaitingInput(
        field_key=field.name,
        label=field.label,
        type=input_type,
        required=field.required,
        placeholder=field.question,
        options=[],
        min=awaiting_input_min(field, state),
        max=None,
        value_schema=awaiting_value_schema(input_type),
    )


def enum_input_for_field(field) -> AwaitingInput | None:
    """将枚举字段转换为前端单选控件。"""
    if not field.options:
        return None
    option_values = field.option_values or [
        {"label": option, "value": option} for option in field.options
    ]
    return AwaitingInput(
        field_key=field.name,
        label=field.label,
        type="single_select",
        required=field.required,
        placeholder=field.question,
        options=option_values,
    )


def awaiting_input_type_for_field(field) -> str:
    """根据模板字段类型选择前端输入控件类型。"""
    if field.type == "date":
        return field.input_type or "datetime"
    if field.input_type in {"textarea", "address"}:
        return field.input_type
    return "text"


def awaiting_input_min(field, state: ApprovalState):
    """为结束时间控件补充最小值约束，避免早于开始时间。"""
    if field.type != "date":
        return None
    if not field.name.endswith("end_time"):
        return None
    start_field = field.name.removesuffix("end_time") + "start_time"
    value = state.get("collected_values", {}).get(start_field)
    if isinstance(value, dict) and value.get("value"):
        return value["value"]
    return state.get("collected_slots", {}).get(start_field)


def awaiting_value_schema(input_type: str) -> dict[str, str] | None:
    """返回复杂控件值结构，供前端按约定提交结构化 answer。"""
    if input_type == "address":
        return {"area": "array", "detail": "string"}
    return None


def template_choice_input(templates: list[ApprovalTemplate]) -> AwaitingInput | None:
    """构建审批模板候选单选控件。"""
    if not templates:
        return None
    return AwaitingInput(
        field_key="__approval_template__",
        label="审批模板",
        type="single_select",
        required=True,
        placeholder="请选择审批模板",
        options=[
            {"label": template.title, "value": template.approval_type}
            for template in templates
        ],
    )

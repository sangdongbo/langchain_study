from __future__ import annotations

from app.schemas.approval import ApprovalAssignee, ApprovalNode
from app.schemas.chat import AwaitingInput, PreviewField


def awaiting_assignee_node_id(awaiting_field: str | None) -> str | None:
    """从等待字段标记中解析审批节点 ID。"""
    if not awaiting_field or not awaiting_field.startswith("assignee:"):
        return None
    return awaiting_field.split(":", 1)[1]


def select_assignees_from_answer(
    node: ApprovalNode,
    answer: dict[str, object] | None,
) -> list[ApprovalAssignee]:
    """根据前端结构化选择从候选审批人中取值。"""
    if not isinstance(answer, dict):
        return []
    expected_field = f"__approval_assignee__:{node.node_id}"
    if answer.get("field_key") != expected_field:
        return []
    raw_value = answer.get("value")
    values = raw_value if isinstance(raw_value, list) else [raw_value]
    selected_uids = {str(value).strip() for value in values if str(value or "").strip()}
    if not selected_uids:
        return []
    selected = [
        assignee
        for assignee in node.candidate_assignees
        if assignee.uid in selected_uids
    ]
    if selected and not node.multiple:
        return selected[:1]
    return selected


def select_assignees_from_message(
    node: ApprovalNode,
    message: str,
) -> list[ApprovalAssignee]:
    """根据用户消息从候选审批人中选择匹配项。"""
    selected = [
        assignee
        for assignee in node.candidate_assignees
        if assignee.name and assignee.name in message
    ]
    if not selected:
        selected = [
            assignee
            for assignee in node.candidate_assignees
            if assignee.uid and assignee.uid in message
        ]
    if selected and not node.multiple:
        return selected[:1]
    return selected


def first_unselected_node(
    nodes: list[ApprovalNode],
    selected_assignees: dict[str, list[str]],
) -> ApprovalNode | None:
    """返回第一个需要用户选择且尚未选择审批人的节点。"""
    for node in nodes:
        if node.requires_selection and not selected_assignees.get(node.node_id):
            return node
    return None


def assignee_selection_message(node: ApprovalNode) -> str:
    """构建审批人选择追问文案。"""
    names = "、".join(assignee.name for assignee in node.candidate_assignees)
    if names:
        return f"请选择{node.node_name}审批人，可选：{names}。"
    return f"请选择{node.node_name}审批人。"


def assignee_selection_input(node: ApprovalNode) -> AwaitingInput:
    """构建审批节点办理人选择控件。"""
    label = f"{node.node_name}审批人"
    return AwaitingInput(
        field_key=f"__approval_assignee__:{node.node_id}",
        label=label,
        type="user_select",
        required=True,
        placeholder=f"请选择{label}",
        options=[
            {
                "label": assignee.name,
                "value": assignee.uid,
                "avatar": assignee.avatar,
            }
            for assignee in node.candidate_assignees
        ],
        multiple=node.multiple,
    )


def assignee_preview_fields(
    nodes: list[ApprovalNode],
    selected_assignees: dict[str, list[str]],
) -> list[PreviewField]:
    """构建审批人预览字段。"""
    fields: list[PreviewField] = []
    for node in nodes:
        selected_uids = set(selected_assignees.get(node.node_id, []))
        if selected_uids:
            names = [
                assignee.name
                for assignee in node.candidate_assignees
                if assignee.uid in selected_uids
            ]
        else:
            names = [assignee.name for assignee in node.selected_assignees]
        if names:
            fields.append(
                PreviewField(
                    name=f"assignee:{node.node_id}",
                    label=f"{node.node_name}审批人",
                    value="、".join(names),
                )
            )
    return fields

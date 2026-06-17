from __future__ import annotations

from copy import deepcopy
from typing import Any

from app.schemas.approval import ApprovalNode


def remote_submit_nodes(
    approval_nodes: list[dict[str, Any]],
    selected_assignees: dict[str, list[str]],
) -> list[dict[str, Any]]:
    """构建创建审批接口需要的 node_list。"""
    nodes = [ApprovalNode(**item) for item in approval_nodes]
    submit_nodes: list[dict[str, Any]] = []
    for node in nodes:
        selected_uids = selected_assignees.get(node.node_id, [])
        if selected_uids:
            users = [
                user
                for user in node.candidate_assignees
                if user.uid in set(selected_uids)
            ]
        else:
            users = node.selected_assignees
        submit_node = _base_submit_node(node)
        submit_node["handle_uids"] = [_int_uid(user.uid) for user in users]
        submit_node["handle_uids_info"] = [
            {
                "uid": _int_uid(user.uid),
                "name": user.name,
                "avatar": user.avatar,
            }
            for user in users
        ]
        submit_node.setdefault("cc_uid_types", [])
        submit_node.setdefault("cc_uids_info", [])
        submit_node.setdefault("cc_uids", [])
        submit_node.setdefault("cc_handle_uids", [])
        submit_node.setdefault("assign_users", [])
        submit_nodes.append(submit_node)
    return submit_nodes


def remote_form_data(slots: dict[str, Any]) -> dict[str, Any]:
    """构建创建审批接口需要的 form_data。"""
    form_data: dict[str, Any] = {}
    for key, value in slots.items():
        if isinstance(value, (dict, list)):
            form_data[key] = value
        else:
            form_data[key] = {"value": value}
    return form_data


def _base_submit_node(node: ApprovalNode) -> dict[str, Any]:
    """基于 CRM 原始节点构建提交节点，避免丢失接口需要的字段。"""
    if node.raw_node:
        return deepcopy(node.raw_node)
    return {
        "id": int(node.node_id),
        "type": node.node_type,
        "name": node.node_name,
        "level": node.level,
    }


def _int_uid(uid: str) -> int:
    """将审批人 UID 转为创建接口使用的整数。"""
    return int(uid)

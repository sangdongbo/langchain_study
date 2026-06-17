from __future__ import annotations

from app.services.approval_payload_builder import (
    remote_form_data,
    remote_submit_nodes,
)


def test_remote_form_data_wraps_scalar_values_and_preserves_structured_values() -> None:
    assert remote_form_data(
        {
            "content": "请假",
            "attachments": [],
            "holiday_rule": {"label": "事假", "value": 13},
        }
    ) == {
        "content": {"value": "请假"},
        "attachments": [],
        "holiday_rule": {"label": "事假", "value": 13},
    }


def test_remote_submit_nodes_preserves_raw_node_and_selected_assignees() -> None:
    nodes = [
        {
            "node_id": "12204",
            "node_name": "办理",
            "node_type": "conduct",
            "level": 3,
            "handle_type": "submitter_choice",
            "multiple": False,
            "requires_selection": True,
            "candidate_assignees": [
                {"uid": "864", "name": "张三", "avatar": None},
                {"uid": "865", "name": "李四", "avatar": "https://example.com/a.jpg"},
            ],
            "selected_assignees": [],
            "raw_node": {
                "id": 12204,
                "pid": 12203,
                "type": "conduct",
                "name": "办理",
                "field_auth": [{"field_key": "content", "field_auth": 1}],
            },
        }
    ]

    submit_nodes = remote_submit_nodes(nodes, {"12204": ["865"]})

    assert submit_nodes == [
        {
            "id": 12204,
            "pid": 12203,
            "type": "conduct",
            "name": "办理",
            "field_auth": [{"field_key": "content", "field_auth": 1}],
            "handle_uids": [865],
            "handle_uids_info": [
                {"uid": 865, "name": "李四", "avatar": "https://example.com/a.jpg"}
            ],
            "cc_uid_types": [],
            "cc_uids_info": [],
            "cc_uids": [],
            "cc_handle_uids": [],
            "assign_users": [],
        }
    ]

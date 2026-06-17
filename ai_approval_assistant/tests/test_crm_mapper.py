from __future__ import annotations

from app.schemas.approval import UserContext
from app.services.crm_mapper import (
    fields_from_remote_payload,
    nodes_from_remote_payload,
    templates_from_remote_payload,
)


def _user() -> UserContext:
    return UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        authorization="Bearer test-token",
        uid="863",
    )


class DynamicOptionProvider:
    def get_holiday_rules(self, user: UserContext) -> list[dict[str, object]]:
        return [{"id": 13, "name": "事假", "balance_rule": 0}]

    def get_related_list(
        self,
        user: UserContext,
        relate_type: str,
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> list[dict[str, object]]:
        return [{"id": 1, "order_num": "SO-001"}]


def test_templates_from_remote_payload_maps_erp_groups() -> None:
    templates = templates_from_remote_payload(
        {
            "data": [
                {
                    "name": "zh-测试",
                    "approvals": [
                        {
                            "id": 5911,
                            "name": "测试外出",
                            "approval_type": "go_out",
                            "is_common": True,
                        }
                    ],
                }
            ]
        }
    )

    assert templates[0].approval_type == "remote_5911"
    assert templates[0].template_id == "5911"
    assert templates[0].title == "测试外出"
    assert templates[0].category == "zh-测试"
    assert "外出" in templates[0].intent_keywords
    assert "go_out" in templates[0].aliases
    assert templates[0].is_common is True


def test_fields_from_remote_payload_resolves_required_dynamic_and_related_options() -> None:
    fields = fields_from_remote_payload(
        {
            "data": [
                {
                    "field_key": "control_rest",
                    "field_name": "请假控件组",
                    "field_type": "control",
                    "sort": 1,
                    "_child": [
                        {
                            "field_key": "rest_holiday_rule_id",
                            "field_name": "请假类型",
                            "field_type": "radio",
                            "is_required": 1,
                            "sort": 1,
                        },
                        {
                            "field_key": "order_id",
                            "field_name": "关联订单",
                            "field_type": "checkbox_order",
                            "is_required": 1,
                            "sort": 2,
                        },
                        {
                            "field_key": "optional_text",
                            "field_name": "非必填文本",
                            "field_type": "input",
                            "is_required": 0,
                            "sort": 3,
                        },
                    ],
                }
            ]
        },
        option_provider=DynamicOptionProvider(),
        user=_user(),
    )

    assert [field["name"] for field in fields] == ["rest_holiday_rule_id", "order_id"]
    assert fields[0]["type"] == "enum"
    assert fields[0]["input_type"] == "single_select"
    assert fields[0]["option_values"] == [{"label": "事假", "value": 13}]
    assert fields[1]["option_values"] == [{"label": "SO-001", "value": "SO-001"}]
    assert fields[0]["group_key"] == "control_rest"


def test_nodes_from_remote_payload_maps_assignee_selection() -> None:
    nodes = nodes_from_remote_payload(
        {
            "data": [
                {
                    "id": 12204,
                    "type": "conduct",
                    "name": "办理",
                    "level": 3,
                    "handle": {
                        "type": "submitter_choice",
                        "is_single": 1,
                        "relate_user": [
                            {"uid": 864, "display_name": "张三"},
                            {"uid": 865, "name": "李四"},
                        ],
                    },
                }
            ]
        }
    )

    assert nodes[0].node_id == "12204"
    assert nodes[0].requires_selection is True
    assert nodes[0].multiple is False
    assert [user.name for user in nodes[0].candidate_assignees] == ["张三", "李四"]

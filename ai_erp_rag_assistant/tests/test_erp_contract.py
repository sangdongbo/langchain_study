from ai_erp_rag_assistant.app.services.erp_client import (
    ErpClient,
    _approval_items,
    _normalize_fields,
)
from ai_erp_rag_assistant.app.services.approval_form_service import (
    build_submit_nodes,
    normalize_approval_nodes,
    normalize_erp_fields,
)
from ai_erp_rag_assistant.app.services.audit_log_service import sanitize_for_log


def test_normalize_fields_uses_real_erp_field_contract():
    fields = _normalize_fields(
        [
            {
                "field_key": "rest_holiday_rule_id",
                "field_name": "假期类型",
                "field_type": "select",
                "is_required": 1,
                "extend": {"options": [{"label": "事假", "value": 7}]},
            },
            {
                "field_key": "rest_start_time",
                "field_name": "开始时间",
                "field_type": "datetime",
                "is_required": 1,
            },
        ]
    )

    assert fields == [
        {
            "name": "rest_holiday_rule_id",
            "label": "假期类型",
            "required": True,
            "type": "enum",
            "erp_field_type": "select",
            "options": ["事假"],
            "option_values": [{"label": "事假", "value": 7}],
            "input_type": "",
        },
        {
            "name": "rest_start_time",
            "label": "开始时间",
            "required": True,
            "type": "datetime",
            "erp_field_type": "datetime",
            "options": [],
            "option_values": [],
            "input_type": "",
        },
    ]


def test_remote_list_flattens_grouped_approval_payload(monkeypatch):
    client = ErpClient()
    client.settings.erp_read_mode = "remote"
    monkeypatch.setattr(
        client,
        "_post",
        lambda path, body, user: {
            "code": 200,
            "data": [{"name": "行政", "approvals": [{"id": 5911, "name": "请假申请"}]}],
        },
    )

    templates = client.list_approval_templates("事假", company_id="C001", user={})

    assert templates == [
        {
            "template_id": "5911",
            "title": "请假申请",
            "description": "",
            "category": "行政",
            "group_name": "行政",
            "template_type": "",
            "company_id": "C001",
        }
    ]


def test_approval_items_preserves_nested_parent_group():
    items = _approval_items(
        {
            "groups": [
                {
                    "name": "人事审批",
                    "items": [{"id": 5911, "name": "请假申请"}],
                }
            ]
        }
    )

    assert items[0]["group_name"] == "人事审批"
    assert items[0]["category"] == "人事审批"


def test_remote_list_maps_leave_subtype_and_filters_unrelated_catalog(monkeypatch):
    client = ErpClient()
    client.settings.erp_read_mode = "remote"
    monkeypatch.setattr(
        client,
        "_post",
        lambda path, body, user: {
            "code": 200,
            "data": [
                {
                    "name": "行政",
                    "approvals": [
                        {"id": 5911, "name": "请假申请"},
                        {"id": 5912, "name": "办公用品入库"},
                    ],
                },
                {
                    "name": "自动化测试",
                    "approvals": [{"id": 5913, "name": "审批测试模板"}],
                },
            ],
        },
    )

    templates = client.list_approval_templates("帮我明天下午请半天病假", company_id="C001", user={})

    assert [item["template_id"] for item in templates] == ["5911"]
    assert templates[0]["title"] == "请假申请"


def test_remote_list_keeps_multiple_real_leave_candidates(monkeypatch):
    client = ErpClient()
    client.settings.erp_read_mode = "remote"
    monkeypatch.setattr(
        client,
        "_post",
        lambda path, body, user: {
            "code": 200,
            "data": [
                {
                    "name": "人事",
                    "approvals": [
                        {"id": 5911, "name": "请假申请"},
                        {"id": 5914, "name": "海外员工休假申请"},
                        {"id": 5915, "name": "费用报销"},
                    ],
                }
            ],
        },
    )

    templates = client.list_approval_templates("事假", company_id="C001", user={})

    assert [item["template_id"] for item in templates] == ["5911", "5914"]


def test_specific_leave_request_does_not_fall_back_to_full_catalog(monkeypatch):
    client = ErpClient()
    client.settings.erp_read_mode = "remote"
    requested_keywords: list[str] = []

    def fake_post(path, body, user):
        requested_keywords.append(body["keyword"])
        return {
            "code": 200,
            "data": [
                {
                    "name": "行政",
                    "approvals": [
                        {"id": 5912, "name": "办公用品入库"},
                        {"id": 5915, "name": "费用报销"},
                    ],
                }
            ],
        }

    monkeypatch.setattr(client, "_post", fake_post)

    templates = client.list_approval_templates("病假", company_id="C001", user={})

    assert templates == []
    assert "" not in requested_keywords
    assert "请假" in requested_keywords


def test_disabled_write_returns_preview_only(monkeypatch):
    client = ErpClient()
    client.settings.erp_write_mode = "disabled"
    add_calls: list[str] = []
    monkeypatch.setattr(client, "_post", lambda *args, **kwargs: add_calls.append("called"))

    result = client.submit_approval(
        {"template_id": "5911", "fields": {"content": "演示"}, "idempotency_key": "demo-key"},
        user={"erp_mode": "remote"},
    )

    assert result["erp_write_mode"] == "disabled"
    assert result["status"].startswith("演示模式")
    assert add_calls == []


def test_dynamic_form_contract_keeps_complex_erp_controls_for_frontend():
    fields = normalize_erp_fields(
        [
            {
                "field_key": "control",
                "field_name": "出差控件组",
                "field_type": "control",
                "_child": [
                    {"field_key": "traveler", "field_name": "同行人", "field_type": "user", "is_required": 1},
                    {
                        "field_key": "orders",
                        "field_name": "关联订单",
                        "field_type": "checkbox_order",
                        "is_required": 0,
                    },
                    {
                        "field_key": "lines",
                        "field_name": "行程明细",
                        "field_type": "detail",
                        "is_required": 1,
                        "_child": [{"field_key": "city", "field_name": "城市", "field_type": "input"}],
                    },
                    {"field_key": "proof", "field_name": "附件", "field_type": "upload", "is_required": 0},
                ],
            }
        ]
    )

    assert [field["component"] for field in fields] == [
        "entity-select",
        "related-select",
        "detail-table",
        "attachment",
    ]
    assert fields[0]["group"] == {"key": "control", "label": "出差控件组", "type": "field-group"}
    assert fields[1]["option_source"]["lazy"] is True
    assert fields[2]["children"][0]["name"] == "city"


def test_submitter_choice_contract_preserves_raw_node_and_selection():
    nodes = [
        {
            "id": 22,
            "name": "办理",
            "type": "conduct",
            "handle": {
                "type": "submitter_choice",
                "is_single": 1,
                "relate_user": [{"uid": 863, "name": "张三"}],
            },
        }
    ]

    flow = normalize_approval_nodes(nodes)
    submitted = build_submit_nodes(nodes, {"22": ["863"]})

    assert flow[0]["requires_selection"] is True
    assert submitted[0]["handle_uids"] == [863]
    assert submitted[0]["handle"]["relate_user"][0]["name"] == "张三"


def test_audit_sanitizer_removes_credentials_and_form_values():
    sanitized = sanitize_for_log(
        {
            "authorization": "Bearer secret",
            "form_data": {"reason": "private", "amount": 10},
            "nested": {"token": "private-token"},
        }
    )

    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["form_data"] == {"field_keys": ["reason", "amount"], "field_count": 2}
    assert sanitized["nested"]["token"] == "[REDACTED]"

from ai_erp_rag_assistant.app.services.erp_client import (
    ErpClient,
    _approval_items,
    _normalize_fields,
)


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

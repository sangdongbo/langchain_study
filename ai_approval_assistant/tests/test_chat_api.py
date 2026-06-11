from __future__ import annotations

import os

from fastapi.testclient import TestClient

os.environ["AI_APPROVAL_USE_LLM"] = "false"

from app.main import app  # noqa: E402
from app.schemas.approval import ApprovalAssignee, ApprovalNode, ApprovalTemplate  # noqa: E402
from app.services.session_state_service import session_state_service  # noqa: E402
from app.services.model_service import model_service  # noqa: E402


client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_expense_flow_previews_then_submits_after_confirmation() -> None:
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-expense",
            "user_id": "U001",
            "message": "我要报销餐饮费 2000 元，客户招待，发票已提供",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_confirmation"
    assert body["approval_type"] == "expense"
    assert body["request_id"] is None
    assert "确认提交" in body["assistant_message"]
    assert body["collected_slots"]["amount"] == "2000"

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-expense",
            "user_id": "U001",
            "message": "确认提交",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
    assert body["request_id"].startswith("EX-")
    first_request_id = body["request_id"]
    first_idempotency_key = body["idempotency_key"]

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-expense",
            "user_id": "U001",
            "message": "确认提交",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "submitted"
    assert body["request_id"] == first_request_id
    assert body["idempotency_key"] == first_idempotency_key
    assert "已经提交过" in body["assistant_message"]


def test_purchase_flow_asks_missing_fields() -> None:
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-purchase",
            "user_id": "U001",
            "message": "我要申请采购笔记本电脑",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "collecting"
    assert body["approval_type"] == "purchase"
    assert body["awaiting_field"] == "数量"
    assert body["awaiting_field_key"] == "quantity"
    assert body["awaiting_field_label"] == "数量"
    assert body["missing_field_labels"] == ["数量"]
    assert "数量" in body["assistant_message"]


def test_large_template_library_classifies_inventory_templates() -> None:
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-inbound",
            "user_id": "U001",
            "message": "我要入库键盘，仓库是A仓，10个",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["approval_type"] == "inbound"
    assert body["status"] == "awaiting_confirmation"
    assert body["collected_slots"]["warehouse"] == "A仓"
    assert body["collected_slots"]["quantity"] == "10"


def test_clarification_summarizes_categories_for_many_templates() -> None:
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-clarify-library",
            "user_id": "U001",
            "message": "我要发起一个流程",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "idle"
    assert "常用审批包括" in body["assistant_message"]
    assert "库存管理" in body["assistant_message"]


def test_greeting_uses_general_chat_instead_of_approval_clarification(monkeypatch) -> None:
    session_state_service.clear("S-general-greeting")
    monkeypatch.setattr(model_service, "chat", lambda message: "你好，我可以帮你处理审批，也可以回答普通问题。")

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-general-greeting",
            "user_id": "U001",
            "message": "你好",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "idle"
    assert body["approval_type"] is None
    assert body["assistant_message"] == "你好，我可以帮你处理审批，也可以回答普通问题。"
    assert "审批模板" not in body["assistant_message"]
    assert "general_chat" in body["trace"]


def test_collecting_flow_can_cancel_without_submit() -> None:
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-cancel",
            "user_id": "U001",
            "message": "我要申请采购笔记本电脑",
        },
    )
    assert response.status_code == 200
    assert response.json()["status"] == "collecting"

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-cancel",
            "user_id": "U001",
            "message": "取消",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["request_id"] is None
    assert "没有提交" in body["assistant_message"]


def test_template_driven_seal_flow_uses_different_fields() -> None:
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-seal",
            "user_id": "U001",
            "message": "我要申请用公章，文件名称是销售合同，2份，用途是客户签约",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_confirmation"
    assert body["approval_type"] == "seal"
    assert body["collected_slots"] == {
        "seal_type": "公章",
        "document_name": "销售合同",
        "copies": "2",
        "purpose": "客户签约",
    }
    labels = [field["label"] for field in body["preview"]["fields"]]
    assert labels == ["印章类型", "文件名称", "份数", "用章用途"]
    assert "报销类型" not in body["assistant_message"]


def test_confirmation_without_preview_is_blocked_by_review() -> None:
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-review",
            "user_id": "U001",
            "message": "确认提交",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "idle"
    assert body["request_id"] is None
    assert "办理哪类审批" in body["assistant_message"]
    assert "decision_review" in body["trace"]


def test_llm_can_classify_when_rules_do_not_match(monkeypatch) -> None:
    session_state_service.clear("S-llm-classify")
    monkeypatch.setattr(model_service, "is_enabled", lambda: True)
    monkeypatch.setattr(model_service, "classify_approval_type", lambda message, templates: "seal")
    monkeypatch.setattr(model_service, "review_decision", lambda **kwargs: {})
    monkeypatch.setattr(model_service, "extract_slots", lambda **kwargs: {})

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-llm-classify",
            "user_id": "U001",
            "message": "我要处理一份销售合同，盖两份，用于客户签约",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_type"] == "seal"
    assert body["status"] == "collecting"


def test_chat_can_use_remote_approval_list_credentials(monkeypatch) -> None:
    session_state_service.clear("S-remote-approval-list")

    def fake_list_available_templates(user):
        assert user.authorization == "Bearer test-token"
        assert user.uid == "863"
        return [
            ApprovalTemplate(**{
                "template_id": "6408",
                "approval_type": "remote_6408",
                "title": "zh-请假",
                "category": "zh-测试",
                "group_name": "zh-测试",
                "aliases": ["请假"],
                "intent_keywords": ["zh-请假", "请假"],
                "visibility": "all",
                "enabled": True,
                "is_common": False,
                "sort_order": 100,
                "fields": [
                    {
                        "name": "description",
                        "label": "审批说明",
                        "type": "text",
                        "required": True,
                        "options": [],
                        "aliases": ["说明", "原因"],
                        "extract_patterns": [],
                        "question": "请补充这条审批需要提交的说明。",
                    }
                ],
            })
        ]

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        fake_list_available_templates,
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-approval-list",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要发起zh-请假",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_type"] == "remote_6408"
    assert body["status"] == "collecting"


def test_remote_keyword_search_with_multiple_templates_asks_user_to_choose(monkeypatch) -> None:
    session_state_service.clear("S-remote-template-choice")
    searched_keywords: list[str] = []

    templates = [
        ApprovalTemplate(**{
            "template_id": "5911",
            "approval_type": "remote_5911",
            "title": "测试外出",
            "category": "zh-测试",
            "group_name": "zh-测试",
            "aliases": ["测试外出", "外出"],
            "intent_keywords": ["测试外出", "外出"],
            "fields": [
                {
                    "name": "go_out_start_time",
                    "label": "开始时间",
                    "type": "date",
                    "required": True,
                    "question": "请选择开始时间",
                }
            ],
        }),
        ApprovalTemplate(**{
            "template_id": "5912",
            "approval_type": "remote_5912",
            "title": "测试外出备用",
            "category": "zh-测试",
            "group_name": "zh-测试",
            "aliases": ["测试外出备用", "外出"],
            "intent_keywords": ["测试外出备用", "外出"],
            "fields": [
                {
                    "name": "go_out_start_time",
                    "label": "开始时间",
                    "type": "date",
                    "required": True,
                    "question": "请选择开始时间",
                }
            ],
        }),
    ]

    def fake_search_available_templates(user, keyword):
        searched_keywords.append(keyword)
        return templates

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.search_available_templates",
        fake_search_available_templates,
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: next(
            template for template in templates if template.approval_type == approval_type
        ),
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-template-choice",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "测试外出",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert searched_keywords == ["测试外出"]
    assert body["status"] == "idle"
    assert body["approval_type"] is None
    assert "找到多个审批模板" in body["assistant_message"]
    assert "1. 测试外出" in body["assistant_message"]
    assert "2. 测试外出备用" in body["assistant_message"]
    assert body["awaiting_input"] == {
        "field_key": "__approval_template__",
        "label": "审批模板",
        "type": "single_select",
        "required": True,
        "placeholder": "请选择审批模板",
        "options": [
            {"label": "测试外出", "value": "remote_5911"},
            {"label": "测试外出备用", "value": "remote_5912"},
        ],
        "multiple": None,
        "min": None,
        "max": None,
        "value_schema": None,
    }

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-template-choice",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "测试外出",
            "answer": {
                "field_key": "__approval_template__",
                "type": "single_select",
                "label": "测试外出",
                "value": "remote_5911",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert searched_keywords == ["测试外出"]
    assert body["approval_type"] == "remote_5911"
    assert body["status"] == "collecting"
    assert body["awaiting_field"] == "开始时间"
    assert body["awaiting_field_key"] == "go_out_start_time"


def test_remote_template_load_error_is_not_rewritten_as_empty_template_message(monkeypatch) -> None:
    """远程模板加载失败时，应保留真实错误，避免误导为没有模板。"""
    session_state_service.clear("S-remote-load-error")

    def fake_list_available_templates(user):
        raise ValueError("approval list returned code 401")

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        fake_list_available_templates,
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-load-error",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer expired-token",
            "message": "我要请假",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "error"
    assert body["assistant_message"] == "CRM 登录已过期或授权无效，请刷新页面重新登录后再试。"
    assert "当前没有可发起的审批模板" not in body["assistant_message"]


def test_chat_can_use_remote_credentials_from_headers(monkeypatch) -> None:
    session_state_service.clear("S-remote-headers")

    def fake_list_available_templates(user):
        assert user.authorization == "Bearer header-token"
        assert user.uid == "863"
        return [
            ApprovalTemplate(**{
                "template_id": "6408",
                "approval_type": "remote_6408",
                "title": "zh-请假",
                "category": "zh-测试",
                "group_name": "zh-测试",
                "aliases": ["请假"],
                "intent_keywords": ["zh-请假", "请假"],
                "visibility": "all",
                "enabled": True,
                "is_common": False,
                "sort_order": 100,
                "fields": [
                    {
                        "name": "description",
                        "label": "审批说明",
                        "type": "text",
                        "required": True,
                        "options": [],
                        "aliases": ["说明", "原因"],
                        "extract_patterns": [],
                        "question": "请补充这条审批需要提交的说明。",
                    }
                ],
            })
        ]

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        fake_list_available_templates,
    )

    response = client.post(
        "/api/ai-approval/chat",
        headers={"Authorization": "Bearer header-token", "UID": "863"},
        json={
            "session_id": "S-remote-headers",
            "user_id": "863",
            "message": "我要发起zh-请假",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_type"] == "remote_6408"
    assert body["status"] == "collecting"


def test_remote_credentials_reset_existing_local_mock_session(monkeypatch) -> None:
    session_state_service.clear("S-local-to-remote")
    first_response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-local-to-remote",
            "user_id": "863",
            "message": "我要请假",
        },
    )
    assert first_response.status_code == 200
    assert first_response.json()["approval_type"] == "leave"
    assert first_response.json()["awaiting_field"] == "请假类型"
    assert first_response.json()["awaiting_field_key"] == "leave_type"

    def fake_list_available_templates(user):
        assert user.authorization == "Bearer header-token"
        assert user.uid == "863"
        return [
            ApprovalTemplate(**{
                "template_id": "6408",
                "approval_type": "remote_6408",
                "title": "zh-请假",
                "category": "zh-测试",
                "group_name": "zh-测试",
                "aliases": ["请假"],
                "intent_keywords": ["zh-请假", "请假"],
                "visibility": "all",
                "enabled": True,
                "is_common": False,
                "sort_order": 100,
                "fields": [
                    {
                        "name": "description",
                        "label": "审批说明",
                        "type": "text",
                        "required": True,
                        "options": [],
                        "aliases": ["说明", "原因"],
                        "extract_patterns": [],
                        "question": "请补充这条审批需要提交的说明。",
                    }
                ],
            })
        ]

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        fake_list_available_templates,
    )

    second_response = client.post(
        "/api/ai-approval/chat",
        headers={"Authorization": "Bearer header-token", "UID": "863"},
        json={
            "session_id": "S-local-to-remote",
            "user_id": "863",
            "message": "我要发起zh-请假",
        },
    )

    assert second_response.status_code == 200
    body = second_response.json()
    assert body["approval_type"] == "remote_6408"
    assert body["awaiting_field"] == "审批说明"
    assert body["awaiting_field_key"] == "description"
    assert "leave_type" not in body["assistant_message"]


def test_remote_waiting_field_exposes_label_for_display_and_key_for_program(monkeypatch) -> None:
    """远程字段等待时，对用户展示中文名称，同时保留字段 key 供程序使用。"""
    session_state_service.clear("S-remote-field-label-display")

    template = ApprovalTemplate(
        template_id="6408",
        approval_type="remote_6408",
        title="zh-请假",
        category="zh-测试",
        aliases=["请假"],
        intent_keywords=["请假"],
        fields=[
            {
                "name": "rest_holiday_rule_id",
                "label": "请假类型",
                "type": "enum",
                "required": True,
                "options": ["事假", "年假"],
                "aliases": ["请假类型"],
                "extract_patterns": [],
                "question": "请选择请假类型",
            }
        ],
    )

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-field-label-display",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要请假",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["approval_type"] == "remote_6408"
    assert body["awaiting_field"] == "请假类型"
    assert body["missing_fields"] == ["请假类型"]
    assert body["awaiting_field_key"] == "rest_holiday_rule_id"
    assert body["missing_field_keys"] == ["rest_holiday_rule_id"]
    assert body["awaiting_field_label"] == "请假类型"
    assert body["missing_field_labels"] == ["请假类型"]
    assert body["awaiting_input"] == {
        "field_key": "rest_holiday_rule_id",
        "label": "请假类型",
        "type": "single_select",
        "required": True,
        "placeholder": "请选择请假类型",
        "options": [
            {"label": "事假", "value": "事假"},
            {"label": "年假", "value": "年假"},
        ],
        "multiple": None,
        "min": None,
        "max": None,
        "value_schema": None,
    }


def test_structured_single_select_answer_is_collected(monkeypatch) -> None:
    session_state_service.clear("S-remote-single-select-answer")

    template = ApprovalTemplate(
        template_id="6408",
        approval_type="remote_6408",
        title="zh-请假",
        category="zh-测试",
        aliases=["请假"],
        intent_keywords=["请假"],
        fields=[
            {
                "name": "rest_holiday_rule_id",
                "label": "请假类型",
                "type": "enum",
                "required": True,
                "options": ["调休假（余8小时）", "事假"],
                "option_values": [
                    {"label": "调休假（余8小时）", "value": 11},
                    {"label": "事假", "value": 13},
                ],
                "aliases": ["请假类型"],
                "extract_patterns": [],
                "question": "请选择请假类型",
            },
            {
                "name": "rest_content",
                "label": "请假事由",
                "type": "text",
                "required": True,
                "options": [],
                "aliases": ["请假事由"],
                "extract_patterns": [],
                "question": "请输入请假事由",
            },
        ],
    )

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )

    first_response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-single-select-answer",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要请假",
        },
    )
    assert first_response.json()["awaiting_input"]["options"][1] == {
        "label": "事假",
        "value": 13,
    }

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-single-select-answer",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "事假",
            "answer": {
                "field_key": "rest_holiday_rule_id",
                "type": "single_select",
                "label": "事假",
                "value": 13,
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["collected_slots"]["rest_holiday_rule_id"] == "事假"
    assert body["collected_values"]["rest_holiday_rule_id"] == {
        "label": "事假",
        "value": 13,
    }
    assert body["awaiting_field"] == "请假事由"


def test_remote_datetime_field_returns_datetime_awaiting_input(monkeypatch) -> None:
    session_state_service.clear("S-remote-datetime-input")

    template = ApprovalTemplate(
        template_id="5904",
        approval_type="remote_5904",
        title="审批编辑-请假控件组",
        category="测试",
        aliases=["请假"],
        intent_keywords=["请假"],
        fields=[
            {
                "name": "rest_start_time",
                "label": "开始时间",
                "type": "date",
                "input_type": "datetime",
                "required": True,
                "options": [],
                "aliases": ["开始时间"],
                "extract_patterns": [],
                "question": "请选择开始时间",
            }
        ],
    )

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-datetime-input",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要请假",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["awaiting_input"] == {
        "field_key": "rest_start_time",
        "label": "开始时间",
        "type": "datetime",
        "required": True,
        "placeholder": "请选择开始时间",
        "options": [],
        "multiple": None,
        "min": None,
        "max": None,
        "value_schema": None,
    }


def test_remote_end_datetime_uses_start_time_as_min(monkeypatch) -> None:
    session_state_service.clear("S-remote-datetime-min")

    template = ApprovalTemplate(
        template_id="5904",
        approval_type="remote_5904",
        title="审批编辑-请假控件组",
        category="测试",
        aliases=["请假"],
        intent_keywords=["请假"],
        fields=[
            {
                "name": "rest_start_time",
                "label": "开始时间",
                "type": "date",
                "input_type": "datetime",
                "required": True,
                "question": "请选择开始时间",
            },
            {
                "name": "rest_end_time",
                "label": "结束时间",
                "type": "date",
                "input_type": "datetime",
                "required": True,
                "question": "请选择结束时间",
            },
        ],
    )

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )

    client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-datetime-min",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要请假",
        },
    )
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-datetime-min",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "2026-06-12 09:00",
            "answer": {
                "field_key": "rest_start_time",
                "type": "datetime",
                "label": "2026-06-12 09:00",
                "value": "2026-06-12 09:00:00",
            },
        },
    )

    body = response.json()
    assert body["awaiting_input"]["field_key"] == "rest_end_time"
    assert body["awaiting_input"]["type"] == "datetime"
    assert body["awaiting_input"]["min"] == "2026-06-12 09:00:00"


def test_remote_address_field_returns_address_awaiting_input(monkeypatch) -> None:
    session_state_service.clear("S-remote-address-input")

    template = ApprovalTemplate(
        template_id="5911",
        approval_type="remote_5911",
        title="测试外出",
        category="测试",
        aliases=["外出"],
        intent_keywords=["外出"],
        fields=[
            {
                "name": "go_out_addr",
                "label": "外出地点",
                "type": "text",
                "input_type": "address",
                "required": True,
                "question": "请选择外出地点",
            }
        ],
    )

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-address-input",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要外出",
        },
    )

    body = response.json()
    assert body["awaiting_input"]["type"] == "address"
    assert body["awaiting_input"]["value_schema"] == {
        "area": "array",
        "detail": "string",
    }


def test_remote_waiting_field_uses_collected_template_label_if_detail_reload_fails(monkeypatch) -> None:
    """响应阶段模板详情重载失败时，也不应把远程字段 key 暴露给用户。"""
    session_state_service.clear("S-remote-field-label-cache")

    template = ApprovalTemplate(
        template_id="6408",
        approval_type="remote_6408",
        title="zh-请假",
        category="zh-测试",
        aliases=["请假"],
        intent_keywords=["请假"],
        fields=[
            {
                "name": "rest_holiday_rule_id",
                "label": "请假类型",
                "type": "enum",
                "required": True,
                "options": ["事假", "年假"],
                "aliases": ["请假类型"],
                "extract_patterns": [],
                "question": "请选择请假类型",
            }
        ],
    )
    detail_calls = 0

    def fake_get_template_detail(approval_type, user):
        nonlocal detail_calls
        detail_calls += 1
        if detail_calls == 1:
            return template
        raise ValueError("form fields reload failed")

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        fake_get_template_detail,
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-field-label-cache",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要请假",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["assistant_message"] == "请选择请假类型"
    assert body["awaiting_field"] == "请假类型"
    assert body["missing_fields"] == ["请假类型"]
    assert body["awaiting_field_key"] == "rest_holiday_rule_id"
    assert body["awaiting_field_label"] == "请假类型"


def test_remote_waiting_enum_field_without_options_accepts_current_reply(monkeypatch) -> None:
    """远程枚举字段没有 options 时，用户回答当前等待字段也应被收集，避免反复追问。"""
    session_state_service.clear("S-remote-enum-no-options")

    template = ApprovalTemplate(
        template_id="6408",
        approval_type="remote_6408",
        title="zh-请假",
        category="zh-测试",
        aliases=["请假"],
        intent_keywords=["请假"],
        fields=[
            {
                "name": "rest_holiday_rule_id",
                "label": "请假类型",
                "type": "enum",
                "required": True,
                "options": [],
                "aliases": ["请假类型"],
                "extract_patterns": [],
                "question": "请选择请假类型",
            },
            {
                "name": "rest_content",
                "label": "请假事由",
                "type": "text",
                "required": True,
                "options": [],
                "aliases": ["请假事由"],
                "extract_patterns": [],
                "question": "请输入请假事由",
            },
        ],
    )

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-enum-no-options",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要请假",
        },
    )
    assert response.json()["awaiting_field_key"] == "rest_holiday_rule_id"

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-enum-no-options",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "事假",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["collected_slots"]["rest_holiday_rule_id"] == "事假"
    assert body["awaiting_field"] == "请假事由"
    assert body["awaiting_field_key"] == "rest_content"


def test_flow_asks_assignee_selection_before_preview(monkeypatch) -> None:
    session_state_service.clear("S-assignee-selection")

    def fake_list_available_templates(user):
        return [
            ApprovalTemplate(
                template_id="5904",
                approval_type="remote_5904",
                title="请假-审批编辑",
                category="测试",
                aliases=["请假"],
                intent_keywords=["请假"],
                fields=[
                        {
                            "name": "reason",
                            "label": "请假原因",
                            "type": "text",
                            "required": True,
                            "aliases": ["原因"],
                            "extract_patterns": ["原因是(.+)"],
                            "question": "请输入请假原因。",
                        }
                ],
            )
        ]

    def fake_get_template_detail(approval_type, user):
        return fake_list_available_templates(user)[0]

    def fake_get_approval_nodes(approval_set_id, form_value, user):
        assert approval_set_id == "5904"
        assert form_value == [{"field_key": "reason", "value": "家中有事"}]
        return [
            ApprovalNode(
                node_id="12204",
                node_name="办理",
                node_type="conduct",
                level=3,
                handle_type="submitter_choice",
                requires_selection=True,
                candidate_assignees=[
                    ApprovalAssignee(uid="864", name="张三"),
                    ApprovalAssignee(uid="865", name="李四"),
                ],
            )
        ]

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        fake_list_available_templates,
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        fake_get_template_detail,
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_approval_nodes",
        fake_get_approval_nodes,
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.validate_approval",
        lambda approval_type, slots, user: type(
            "Validation",
            (),
            {
                "valid": True,
                "errors": [],
                "field_errors": [],
                "warnings": [],
                "approval_node": None,
            },
        )(),
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-assignee-selection",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要请假，原因是家中有事",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_assignee_selection"
    assert body["approval_type"] == "remote_5904"
    assert body["awaiting_field"] == "assignee:12204"
    assert body["awaiting_input"] == {
        "field_key": "__approval_assignee__:12204",
        "label": "办理审批人",
        "type": "user_select",
        "required": True,
        "placeholder": "请选择办理审批人",
        "options": [
            {"label": "张三", "value": "864", "avatar": None},
            {"label": "李四", "value": "865", "avatar": None},
        ],
        "multiple": False,
        "min": None,
        "max": None,
        "value_schema": None,
    }
    assert "请选择办理审批人" in body["assistant_message"]
    assert "张三" in body["assistant_message"]
    assert "李四" in body["assistant_message"]
    assert "assignee" in body["trace"]


def test_flow_accepts_structured_assignee_selection_then_previews(monkeypatch) -> None:
    session_state_service.clear("S-assignee-structured-selected")

    template = ApprovalTemplate(
        template_id="5904",
        approval_type="remote_5904",
        title="请假-审批编辑",
        category="测试",
        aliases=["请假"],
        intent_keywords=["请假"],
        fields=[
            {
                "name": "reason",
                "label": "请假原因",
                "type": "text",
                "required": True,
                "aliases": ["原因"],
                "extract_patterns": ["原因是(.+)"],
                "question": "请输入请假原因。",
            }
        ],
    )
    nodes = [
        ApprovalNode(
            node_id="12204",
            node_name="办理",
            node_type="conduct",
            level=3,
            handle_type="submitter_choice",
            requires_selection=True,
            candidate_assignees=[
                ApprovalAssignee(uid="864", name="张三"),
                ApprovalAssignee(uid="865", name="李四"),
            ],
        )
    ]

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_approval_nodes",
        lambda approval_set_id, form_value, user: nodes,
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.validate_approval",
        lambda approval_type, slots, user: type(
            "Validation",
            (),
            {
                "valid": True,
                "errors": [],
                "field_errors": [],
                "warnings": [],
                "approval_node": None,
            },
        )(),
    )

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-assignee-structured-selected",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要请假，原因是家中有事",
        },
    )
    assert response.json()["status"] == "awaiting_assignee_selection"

    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-assignee-structured-selected",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "选择办理人",
            "answer": {
                "field_key": "__approval_assignee__:12204",
                "type": "user_select",
                "label": "张三",
                "value": "864",
            },
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_confirmation"
    assert body["awaiting_field"] is None
    assert "确认提交" in body["assistant_message"]
    assert "张三" in body["assistant_message"]


def test_remote_confirmation_passes_nodes_to_submit(monkeypatch) -> None:
    session_state_service.clear("S-remote-submit")
    submitted: dict[str, object] = {}

    template = ApprovalTemplate(
        template_id="5904",
        approval_type="remote_5904",
        title="请假-审批编辑",
        category="测试",
        aliases=["请假"],
        intent_keywords=["请假"],
        fields=[
            {
                "name": "reason",
                "label": "请假原因",
                "type": "text",
                "required": True,
                "aliases": ["原因"],
                "extract_patterns": ["原因是(.+)"],
                "question": "请输入请假原因。",
            }
        ],
    )
    nodes = [
        ApprovalNode(
            node_id="12204",
            node_name="办理",
            node_type="conduct",
            level=3,
            handle_type="submitter_choice",
            requires_selection=True,
            candidate_assignees=[ApprovalAssignee(uid="864", name="张三")],
        )
    ]

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.get_approval_nodes",
        lambda approval_set_id, form_value, user: nodes,
    )
    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.validate_approval",
        lambda approval_type, slots, user: type(
            "Validation",
            (),
            {
                "valid": True,
                "errors": [],
                "field_errors": [],
                "warnings": [],
                "approval_node": None,
            },
        )(),
    )

    def fake_submit_approval(
        approval_type,
        slots,
        user,
        idempotency_key,
        approval_set_id=None,
        approval_nodes=None,
        selected_assignees=None,
    ):
        submitted.update(
            {
                "approval_type": approval_type,
                "approval_set_id": approval_set_id,
                "approval_nodes": approval_nodes,
                "selected_assignees": selected_assignees,
            }
        )
        return type(
            "Submit",
            (),
            {
                "request_id": "AP202606100001",
                "status": "待审批",
                "approval_node": "CRM审批流",
                "idempotency_key": None,
            },
        )()

    monkeypatch.setattr(
        "app.graph.workflow.crm_approval_service.submit_approval",
        fake_submit_approval,
    )

    client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-submit",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "我要请假，原因是家中有事",
        },
    )
    client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-submit",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "选张三",
        },
    )
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-remote-submit",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "确认提交",
        },
    )

    assert response.status_code == 200
    assert response.json()["status"] == "submitted"
    assert submitted["approval_type"] == "remote_5904"
    assert submitted["approval_set_id"] == "5904"
    assert submitted["selected_assignees"] == {"12204": ["864"]}
    assert submitted["approval_nodes"][0]["node_id"] == "12204"


def test_validation_returns_field_errors() -> None:
    response = client.post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-field-errors",
            "user_id": "U001",
            "message": "我要请病假，从2026-06-03到2026-06-01，因为发烧",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "collecting"
    assert "开始时间不能晚于结束时间" in body["assistant_message"]
    assert {"field": "start_date", "message": "开始时间不能晚于结束时间。"} in body["field_errors"]
    assert {"field": "end_date", "message": "开始时间不能晚于结束时间。"} in body["field_errors"]

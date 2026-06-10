from __future__ import annotations

import os

from fastapi.testclient import TestClient

os.environ["AI_APPROVAL_USE_LLM"] = "false"

from ai_approval_assistant.app.main import app  # noqa: E402
from ai_approval_assistant.app.schemas.approval import ApprovalAssignee, ApprovalNode, ApprovalTemplate  # noqa: E402
from ai_approval_assistant.app.services.session_state_service import session_state_service  # noqa: E402
from ai_approval_assistant.app.services.model_service import model_service  # noqa: E402


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
    assert body["awaiting_field"] == "quantity"
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
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.list_available_templates",
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
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.list_available_templates",
        fake_list_available_templates,
    )
    monkeypatch.setattr(
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.get_template_detail",
        fake_get_template_detail,
    )
    monkeypatch.setattr(
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.get_approval_nodes",
        fake_get_approval_nodes,
    )
    monkeypatch.setattr(
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.validate_approval",
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
    assert "请选择办理审批人" in body["assistant_message"]
    assert "张三" in body["assistant_message"]
    assert "李四" in body["assistant_message"]
    assert "assignee" in body["trace"]


def test_flow_accepts_assignee_selection_then_previews(monkeypatch) -> None:
    session_state_service.clear("S-assignee-selected")

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
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )
    monkeypatch.setattr(
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.get_approval_nodes",
        lambda approval_set_id, form_value, user: nodes,
    )
    monkeypatch.setattr(
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.validate_approval",
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
            "session_id": "S-assignee-selected",
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
            "session_id": "S-assignee-selected",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "选张三",
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
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.list_available_templates",
        lambda user: [template],
    )
    monkeypatch.setattr(
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.get_template_detail",
        lambda approval_type, user: template,
    )
    monkeypatch.setattr(
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.get_approval_nodes",
        lambda approval_set_id, form_value, user: nodes,
    )
    monkeypatch.setattr(
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.validate_approval",
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
        "ai_approval_assistant.app.graph.workflow.crm_approval_service.submit_approval",
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

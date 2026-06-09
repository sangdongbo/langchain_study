from __future__ import annotations

import os

from fastapi.testclient import TestClient

os.environ["AI_APPROVAL_USE_LLM"] = "false"

from ai_approval_assistant.app.main import app  # noqa: E402
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

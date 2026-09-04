from types import SimpleNamespace

from ai_erp_rag_assistant.app.assistant_catalog import (
    APPROVAL_ASSISTANT_KEY,
    assistant_type_for_key,
)
from ai_erp_rag_assistant.app.models import Assistant
from ai_erp_rag_assistant.app.routes.assistants import assistant_list
from ai_erp_rag_assistant.app.schemas import AssistantListRequest


def test_assistant_type_is_derived_from_server_reserved_key():
    assert assistant_type_for_key(APPROVAL_ASSISTANT_KEY) == "approval"
    assert assistant_type_for_key("employee-rag") == "rag"


def test_unified_assistant_list_merges_fixed_and_rag_assistants(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._persistent_identity",
        lambda request, authorization, uid: (
            request,
            {"company_id": "16", "uid": "863"},
            "16",
            "863",
        ),
    )
    rag_assistant = Assistant(
        id=2,
        company_id="16",
        assistant_key="employee-rag",
        name="员工制度助手",
        status="active",
    )

    class FakeSession:
        @staticmethod
        def scalars(statement):
            return SimpleNamespace(all=lambda: [rag_assistant])

        @staticmethod
        def rollback():
            raise AssertionError("成功路径不应回滚")

    response = assistant_list(
        AssistantListRequest(user_id="863", status="active"),
        authorization="Bearer local-test",
        uid="863",
        db=FakeSession(),
    )

    assert response["count"] == 2
    assert response["items"][0] == {
        "id": None,
        "assistant_key": "approval-assistant",
        "name": "审批助手",
        "assistant_type": "approval",
        "is_system": True,
        "status": "active",
    }
    assert response["items"][1]["assistant_type"] == "rag"
    assert response["items"][1]["is_system"] is False

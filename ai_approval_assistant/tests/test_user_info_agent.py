from __future__ import annotations

from app.agents import approval_agent
from app.agents.approval_agent import intent_router_node
from app.agents.approval_agent import user_info_agent_node
from app.graph.approval_workflow import create_workflow
from app.graph.state import initial_state
from app.tools import user_tools


def test_intent_router_routes_user_superior_question_with_user_word_to_user_info() -> None:
    state = {
        **initial_state("S-user-info-route", "863"),
        "user_message": "我的用户上级是？",
    }

    result = intent_router_node(state)

    assert result["intent"] == "user_info"
    assert result["_route"] == "user_info_agent"


def test_user_info_agent_invokes_user_tools_for_remote_profile(monkeypatch) -> None:
    calls: list[tuple[str, str, str | None, str | None]] = []

    def fake_get_userinfo(user):
        calls.append(("current", user.user_id, user.uid, user.authorization))
        return {"uid": "863", "name": "桑东波", "department_name": "研发部"}

    def fake_get_superior_info(user):
        calls.append(("superior", user.user_id, user.uid, user.authorization))
        return {"uid": "864", "name": "张经理"}

    monkeypatch.setattr(user_tools.user_service, "get_userinfo", fake_get_userinfo)
    monkeypatch.setattr(
        user_tools.user_service,
        "get_superior_info",
        fake_get_superior_info,
    )
    state = {
        **initial_state("S-user-info-tools", "863"),
        "uid": "863",
        "authorization": "Bearer test-token",
        "user_message": "我的用户上级是？",
    }

    result = user_info_agent_node(state)

    assert calls == [
        ("current", "863", "863", "Bearer test-token"),
        ("superior", "863", "863", "Bearer test-token"),
    ]
    assert result["user_profile"] == {
        "uid": "863",
        "name": "桑东波",
        "department_name": "研发部",
    }
    assert result["superior_profile"] == {"uid": "864", "name": "张经理"}
    assert "桑东波" in result["assistant_message"]
    assert "张经理" in result["assistant_message"]
    assert result["trace"][-1] == "user_info_agent"
    assert result["_tool_calls"] == [
        {
            "name": "get_current_user_info",
            "status": "success",
            "result": {
                "uid": "863",
                "name": "桑东波",
                "department_name": "研发部",
            },
        },
        {
            "name": "get_user_superior_info",
            "status": "success",
            "result": {"uid": "864", "name": "张经理"},
        },
    ]


def test_user_info_agent_reuses_loaded_profiles_without_duplicate_tool_calls(
    monkeypatch,
) -> None:
    def fail_get_userinfo(user):
        raise AssertionError("user_info_agent should reuse loaded user_profile")

    def fail_get_superior_info(user):
        raise AssertionError("user_info_agent should reuse loaded superior_profile")

    monkeypatch.setattr(user_tools.user_service, "get_userinfo", fail_get_userinfo)
    monkeypatch.setattr(
        user_tools.user_service,
        "get_superior_info",
        fail_get_superior_info,
    )
    state = {
        **initial_state("S-user-info-reuse", "863"),
        "uid": "863",
        "authorization": "Bearer test-token",
        "user_message": "我的用户上级是？",
        "user_profile": {
            "uid": "863",
            "name": "桑东波",
            "department_name": "研发部",
        },
        "superior_profile": {"uid": "864", "name": "张经理"},
        "_tool_calls": [
            {
                "name": "get_current_user_info",
                "status": "success",
                "result": {"uid": "863", "name": "桑东波"},
            },
            {
                "name": "get_user_superior_info",
                "status": "success",
                "result": {"uid": "864", "name": "张经理"},
            },
        ],
    }

    result = user_info_agent_node(state)

    assert "桑东波" in result["assistant_message"]
    assert "张经理" in result["assistant_message"]
    assert result["_tool_calls"] == state["_tool_calls"]


def test_workflow_does_not_load_user_profile_for_general_chat(monkeypatch) -> None:
    def fail_load_user_profiles(state):
        raise AssertionError("general chat should not load user profile")

    monkeypatch.setattr(approval_agent, "load_user_profiles", fail_load_user_profiles)
    state = {
        **initial_state("S-general-no-profile", "863"),
        "uid": "863",
        "authorization": "Bearer test-token",
        "user_message": "你好",
    }

    result = create_workflow().invoke(state)

    assert result["intent"] == "general_chat"
    assert result["trace"] == ["memory_agent", "intent_router", "general_chat"]

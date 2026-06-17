from __future__ import annotations

from app.agents.user_profile_agent import load_user_profiles
from app.graph.state import initial_state


def test_load_user_profiles_returns_agent_state_profile_updates(monkeypatch) -> None:
    calls: list[str | None] = []

    def fake_get_userinfo(user):
        calls.append(user.uid)
        if user.uid == "863":
            return {"uid": "863", "name": "桑东波", "superior_id": "864"}
        return {"uid": "864", "name": "张经理", "superior_id": "0"}

    monkeypatch.setattr(
        "app.agents.user_profile_agent.user_service.get_userinfo",
        fake_get_userinfo,
    )
    state = {
        **initial_state("S001", "U001"),
        "uid": "863",
        "authorization": "Bearer test-token",
    }

    update = load_user_profiles(state)

    assert calls == ["863", "864"]
    assert update["user_profile"] == {"uid": "863", "name": "桑东波", "superior_id": "864"}
    assert update["superior_profile"] == {"uid": "864", "name": "张经理", "superior_id": "0"}
    assert update["trace"][-1] == "user_profile_agent"
    assert update["_tool_calls"] == [
        {
            "name": "get_current_user_info",
            "status": "success",
            "result": {"uid": "863", "name": "桑东波", "superior_id": "864"},
        },
        {
            "name": "get_user_superior_info",
            "status": "success",
            "result": {"uid": "864", "name": "张经理", "superior_id": "0"},
        },
    ]


def test_load_user_profiles_uses_loaded_superior_id_without_refetching_current_user(
    monkeypatch,
) -> None:
    calls: list[tuple[str, str | None]] = []

    def fake_get_userinfo(user):
        calls.append(("userinfo", user.uid))
        if user.uid == "863":
            return {"uid": "863", "name": "桑东波", "superior_id": "40"}
        return {"uid": "40", "name": "直属上级", "superior_id": "0"}

    monkeypatch.setattr(
        "app.agents.user_profile_agent.user_service.get_userinfo",
        fake_get_userinfo,
    )
    state = {
        **initial_state("S001", "863"),
        "uid": "863",
        "authorization": "Bearer test-token",
    }

    update = load_user_profiles(state)

    assert calls == [("userinfo", "863"), ("userinfo", "40")]
    assert update["user_profile"]["superior_id"] == "40"
    assert update["superior_profile"]["uid"] == "40"
    assert update["superior_profile"]["name"] == "直属上级"


def test_load_user_profiles_skips_without_remote_credentials(monkeypatch) -> None:
    def fail_get_userinfo(user):
        raise AssertionError("userinfo should not be called without remote credentials")

    monkeypatch.setattr(
        "app.agents.user_profile_agent.user_service.get_userinfo",
        fail_get_userinfo,
    )
    state = initial_state("S001", "U001")

    update = load_user_profiles(state)

    assert update["user_profile"] is None
    assert update["superior_profile"] is None
    assert update["trace"][-1] == "user_profile_agent"
    assert update["_tool_calls"] == []


def test_load_user_profiles_keeps_flow_when_userinfo_fails(monkeypatch) -> None:
    def fail_get_userinfo(user):
        raise ValueError("userinfo returned code 401")

    monkeypatch.setattr(
        "app.agents.user_profile_agent.user_service.get_userinfo",
        fail_get_userinfo,
    )
    state = {
        **initial_state("S001", "U001"),
        "uid": "863",
        "authorization": "Bearer test-token",
    }

    update = load_user_profiles(state)

    assert update["user_profile"] is None
    assert update["superior_profile"] is None
    assert update["trace"][-1] == "user_profile_agent"
    assert update["_tool_calls"] == [
        {
            "name": "get_current_user_info",
            "status": "error",
            "error": "userinfo returned code 401",
        }
    ]

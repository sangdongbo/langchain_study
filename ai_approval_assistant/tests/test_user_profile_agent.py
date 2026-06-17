from __future__ import annotations

from app.agents.user_profile_agent import load_user_profiles
from app.graph.state import initial_state


def test_load_user_profiles_returns_agent_state_profile_updates(monkeypatch) -> None:
    calls: list[str] = []

    def fake_get_userinfo(user):
        calls.append("user")
        return {"uid": "863", "name": "桑东波", "superior_id": "864"}

    def fake_get_superior_info(user):
        calls.append("superior")
        return {"uid": "864", "name": "张经理", "superior_id": "0"}

    monkeypatch.setattr(
        "app.agents.user_profile_agent.user_service.get_userinfo",
        fake_get_userinfo,
    )
    monkeypatch.setattr(
        "app.agents.user_profile_agent.user_service.get_superior_info",
        fake_get_superior_info,
    )
    state = {
        **initial_state("S001", "U001"),
        "uid": "863",
        "authorization": "Bearer test-token",
    }

    update = load_user_profiles(state)

    assert calls == ["user", "superior"]
    assert update["user_profile"] == {"uid": "863", "name": "桑东波", "superior_id": "864"}
    assert update["superior_profile"] == {"uid": "864", "name": "张经理", "superior_id": "0"}
    assert update["trace"][-1] == "user_profile_agent"


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

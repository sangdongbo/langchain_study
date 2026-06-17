from __future__ import annotations

from app.tools import USER_TOOLS
from app.tools import user_tools


def test_user_tools_exports_get_current_user_info_tool() -> None:
    names = {tool.name for tool in USER_TOOLS}

    assert "get_current_user_info" in names
    assert "get_user_superior_info" in names


def test_get_current_user_info_tool_invokes_user_service(monkeypatch) -> None:
    calls: list[tuple[str, str | None, str | None]] = []

    def fake_get_userinfo(user):
        calls.append((user.user_id, user.uid, user.authorization))
        return {"uid": "863", "name": "桑东波"}

    monkeypatch.setattr(user_tools.user_service, "get_userinfo", fake_get_userinfo)

    result = user_tools.get_current_user_info.invoke(
        {
            "user_id": "U001",
            "uid": "863",
            "authorization": "Bearer test-token",
        }
    )

    assert result == {"uid": "863", "name": "桑东波"}
    assert calls == [("U001", "863", "Bearer test-token")]


def test_get_user_superior_info_tool_invokes_user_service(monkeypatch) -> None:
    calls: list[tuple[str, str | None, str | None]] = []

    def fake_get_superior_info(user):
        calls.append((user.user_id, user.uid, user.authorization))
        return {"uid": "864", "name": "张经理"}

    monkeypatch.setattr(user_tools.user_service, "get_superior_info", fake_get_superior_info)

    result = user_tools.get_user_superior_info.invoke(
        {
            "user_id": "U001",
            "uid": "863",
            "authorization": "Bearer test-token",
        }
    )

    assert result == {"uid": "864", "name": "张经理"}
    assert calls == [("U001", "863", "Bearer test-token")]

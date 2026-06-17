from __future__ import annotations

from app.schemas.approval import UserContext
from app.services.user_service import UserService


class FakeUserApiClient:
    def get_userinfo(self, user: UserContext) -> dict[str, object]:
        return {
            "code": 200,
            "message": "success",
            "data": {
                "uid": 863,
                "name": "桑东波",
                "display_name": "桑东波",
                "avatar": "https://example.com/a.jpg",
                "mobile": "13800000000",
                "email": "user@example.com",
                "company_id": 1,
                "department_id": 20,
                "department_name": "研发部",
                "superior_id": 864,
            },
        }


def test_get_userinfo_returns_normalized_user_profile() -> None:
    service = UserService(api_client=FakeUserApiClient())
    user = UserContext(
        user_id="U001",
        name="User U001",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid="863",
        authorization="Bearer test-token",
    )

    profile = service.get_userinfo(user)

    assert profile == {
        "uid": "863",
        "name": "桑东波",
        "display_name": "桑东波",
        "avatar": "https://example.com/a.jpg",
        "mobile": "13800000000",
        "email": "user@example.com",
        "company_id": "1",
        "dept_id": "20",
        "department_name": "研发部",
        "superior_id": "864",
        "raw": {
            "uid": 863,
            "name": "桑东波",
            "display_name": "桑东波",
            "avatar": "https://example.com/a.jpg",
            "mobile": "13800000000",
            "email": "user@example.com",
            "company_id": 1,
            "department_id": 20,
            "department_name": "研发部",
            "superior_id": 864,
        },
    }


def test_get_userinfo_requires_remote_credentials() -> None:
    service = UserService(api_client=FakeUserApiClient())
    user = UserContext(
        user_id="U001",
        name="User U001",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
    )

    assert service.get_userinfo(user) == {}


def test_get_superior_info_uses_current_user_superior_id() -> None:
    calls: list[str] = []

    class FakeSuperiorApiClient:
        def get_userinfo(self, user: UserContext) -> dict[str, object]:
            calls.append(user.uid or "")
            if user.uid == "863":
                return {
                    "code": 200,
                    "message": "success",
                    "data": {"uid": 863, "name": "桑东波", "superior_id": 864},
                }
            return {
                "code": 200,
                "message": "success",
                "data": {"uid": 864, "name": "张经理", "superior_id": 0},
            }

    service = UserService(api_client=FakeSuperiorApiClient())
    user = UserContext(
        user_id="U001",
        name="User U001",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid="863",
        authorization="Bearer test-token",
    )

    superior = service.get_superior_info(user)

    assert calls == ["863", "864"]
    assert superior["uid"] == "864"
    assert superior["name"] == "张经理"
    assert superior["superior_id"] == "0"

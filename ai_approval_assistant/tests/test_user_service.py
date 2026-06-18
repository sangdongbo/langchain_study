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


def test_get_userinfo_normalizes_nested_userinfo_payload() -> None:
    class FakeNestedUserApiClient:
        def get_userinfo(self, user: UserContext) -> dict[str, object]:
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "user": {
                        "id": 863,
                        "name": "桑东波",
                        "avatar": "https://example.com/a.jpg",
                        "phone": "13800000000",
                        "email": "user@example.com",
                        "company_id": 16,
                        "department_id": 13,
                        "superior_id": 40,
                    },
                    "company": [],
                    "wechat": None,
                },
            }

    service = UserService(api_client=FakeNestedUserApiClient())
    user = UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid="863",
        authorization="Bearer test-token",
    )

    profile = service.get_userinfo(user)

    assert profile["uid"] == "863"
    assert profile["name"] == "桑东波"
    assert profile["company_id"] == "16"
    assert profile["dept_id"] == "13"
    assert profile["superior_id"] == "40"
    assert profile["raw"]["user"]["superior_id"] == 40


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
    userinfo_calls: list[str] = []
    detail_calls: list[str] = []

    class FakeSuperiorApiClient:
        def get_userinfo(self, user: UserContext) -> dict[str, object]:
            userinfo_calls.append(user.uid or "")
            return {
                "code": 200,
                "message": "success",
                "data": {"uid": 863, "name": "桑东波", "superior_id": 864},
            }

        def get_user_detail(self, user: UserContext, user_id: str) -> dict[str, object]:
            detail_calls.append(user_id)
            return {
                "code": 200,
                "message": "success",
                "data": {
                    "user_id": 864,
                    "name": {"value": "张经理"},
                    "phone": {"value": "13900000000"},
                    "department_id": {"value": [20], "text": []},
                    "company_id": 1,
                    "superior_id": {"value": [], "text": []},
                },
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

    assert userinfo_calls == ["863"]
    assert detail_calls == ["864"]
    assert superior["uid"] == "864"
    assert superior["name"] == "张经理"
    assert superior["superior_id"] == "0"


def test_get_superior_info_skips_second_request_without_superior_id() -> None:
    calls: list[str] = []

    class FakeNoSuperiorApiClient:
        def get_userinfo(self, user: UserContext) -> dict[str, object]:
            calls.append(user.uid or "")
            return {
                "code": 200,
                "message": "success",
                "data": {"uid": 863, "name": "桑东波", "superior_id": 0},
            }

    service = UserService(api_client=FakeNoSuperiorApiClient())
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

    assert calls == ["863"]
    assert superior == {}

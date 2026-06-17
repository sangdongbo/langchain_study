from __future__ import annotations

import httpx

from app.schemas.approval import UserContext
from app.services.user_api_client import UserApiClient


def test_get_userinfo_posts_chat_credentials_to_userinfo_endpoint() -> None:
    requests: list[httpx.Request] = []
    log_events: list[tuple[str, dict[str, object]]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {"uid": 863, "name": "桑东波", "superior_id": 40},
            },
        )

    client = UserApiClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        userinfo_url="https://crm.local/api/User/userinfo",
        log_writer=lambda event, payload: log_events.append((event, payload)),
    )
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

    payload = client.get_userinfo(user)

    assert payload["code"] == 200
    assert requests[0].url.path == "/api/User/userinfo"
    assert requests[0].headers["Authorization"] == "Bearer test-token"
    assert requests[0].headers["UID"] == "863"
    assert requests[0].content == b"{}"
    assert log_events[-1] == (
        "crm.user.userinfo.response",
        {
            "code": 200,
            "message": "success",
            "data_type": "dict",
            "data_keys": ["name", "superior_id", "uid"],
            "data_preview": {
                "id": None,
                "uid": 863,
                "user_id": None,
                "superior_id": 40,
                "superior_uid": None,
                "parent_id": None,
                "leader_id": None,
                "manager_id": None,
            },
        },
    )

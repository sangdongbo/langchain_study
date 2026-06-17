from __future__ import annotations

import json

import httpx

from app.schemas.approval import UserContext
from app.services.crm_api_client import CrmApiClient


def _user() -> UserContext:
    return UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        authorization="Bearer test-token",
        uid="863",
    )


def test_client_methods_wrap_each_crm_endpoint() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "message": "success", "data": []})

    client = CrmApiClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        approval_list_url="https://crm.local/api/approval/list",
        form_fields_url="https://crm.local/api/field/formFields",
        get_nodes_url="https://crm.local/api/approval/getNodes",
        add_approval_url="https://crm.local/api/approval/add",
        related_list_url="https://crm.local/api/Company/getRelatedList",
        holiday_rule_url="https://crm.local/api/attendance/getHolidayRuleByUser",
    )
    user = _user()

    client.list_approvals(user, "测试外出")
    client.get_form_fields(user, "5911")
    client.get_approval_nodes(user, "5911", [{"field_key": "content", "value": "x"}])
    client.get_related_list(user, "crmOrder", keyword="SO", page=2, page_size=10)
    client.get_holiday_rules(user)
    client.add_approval(user, "5911", node_list=[{"id": 1}], form_data={"content": {"value": "x"}})

    assert [request.url.path for request in requests] == [
        "/api/approval/list",
        "/api/field/formFields",
        "/api/approval/getNodes",
        "/api/Company/getRelatedList",
        "/api/attendance/getHolidayRuleByUser",
        "/api/approval/add",
    ]
    assert [request.headers["Authorization"] for request in requests] == [
        "Bearer test-token"
    ] * 6
    assert [request.headers["UID"] for request in requests] == ["863"] * 6
    assert json.loads(requests[0].content) == {"keyword": "测试外出"}
    assert json.loads(requests[1].content) == {"field_form": "approval_type_5911"}
    assert json.loads(requests[2].content) == {
        "approval_set_id": 5911,
        "form_value": [{"field_key": "content", "value": "x"}],
    }
    assert json.loads(requests[3].content) == {
        "relate_type": "crmOrder",
        "page": 2,
        "pageSize": 10,
        "keyword": "SO",
        "status": 0,
        "created_at": "",
        "hasNoAccess": False,
        "type": "",
    }
    assert json.loads(requests[4].content) == {}
    assert json.loads(requests[5].content) == {
        "approval_set_id": 5911,
        "node_list": [{"id": 1}],
        "form_data": {"content": {"value": "x"}},
    }

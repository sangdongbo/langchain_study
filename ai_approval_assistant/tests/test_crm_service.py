from __future__ import annotations

import json

import httpx

from ai_approval_assistant.app.schemas.approval import UserContext
from ai_approval_assistant.app.services.crm_service import CrmApprovalService


def test_remote_approval_list_uses_chat_credentials() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": [
                    {
                        "id": 1371,
                        "name": "zh-测试",
                        "approvals": [
                            {
                                "id": 6408,
                                "name": "zh-请假",
                                "type": "",
                                "approval_type": "",
                                "is_common": True,
                            }
                        ],
                    }
                ],
            },
        )

    service = CrmApprovalService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        approval_list_url="https://dev2.lanerp.com/api/approval/list",
    )
    user = UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        authorization="Bearer test-token",
        uid="863",
    )

    templates = service.list_available_templates(user)

    assert len(templates) == 1
    assert templates[0].template_id == "6408"
    assert templates[0].title == "zh-请假"
    assert templates[0].category == "zh-测试"
    assert requests[0].headers["Authorization"] == "Bearer test-token"
    assert requests[0].headers["UID"] == "863"
    assert requests[0].content == b'{"keyword":""}'


def test_remote_template_detail_loads_form_fields() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/approval/list":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "message": "success",
                    "data": [
                        {
                            "id": 1371,
                            "name": "zh-测试",
                            "approvals": [
                                {
                                    "id": 5911,
                                    "name": "测试外出",
                                    "type": "",
                                    "approval_type": "",
                                    "is_common": False,
                                }
                            ],
                        }
                    ],
                },
            )
        if request.url.path == "/api/field/formFields":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "message": "success",
                    "data": [
                        {
                            "field_key": "control_go_out",
                            "field_name": "外出控件组",
                            "field_type": "control",
                            "is_required": 0,
                            "sort": 1,
                            "_child": [
                                {
                                    "field_key": "go_out_start_time",
                                    "field_name": "开始时间",
                                    "field_type": "date",
                                    "is_required": 1,
                                    "sort": 2,
                                    "extend": {"placeholder": "请选择开始时间"},
                                },
                                {
                                    "field_key": "go_out_end_time",
                                    "field_name": "结束时间",
                                    "field_type": "date",
                                    "is_required": 1,
                                    "sort": 3,
                                    "extend": {"placeholder": "请选择结束时间"},
                                },
                                {
                                    "field_key": "go_out_addr",
                                    "field_name": "外出地点",
                                    "field_type": "address",
                                    "is_required": 1,
                                    "sort": 4,
                                    "extend": {"area_accuracy_placeholder": "请选择外出地点"},
                                },
                                {
                                    "field_key": "go_out_content",
                                    "field_name": "外出事由",
                                    "field_type": "textarea",
                                    "is_required": 1,
                                    "sort": 5,
                                    "extend": {"placeholder": "请输入"},
                                },
                            ],
                        },
                        {
                            "field_key": "field_525792",
                            "field_name": "关联审批单",
                            "field_type": "checkbox_approval",
                            "is_required": 0,
                            "sort": 6,
                        },
                        {
                            "field_key": "field_525823",
                            "field_name": "单行文本",
                            "field_type": "input",
                            "is_required": 0,
                            "sort": 8,
                            "extend": {"placeholder": "请输入"},
                        },
                    ],
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    service = CrmApprovalService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        approval_list_url="https://dev2.lanerp.com/api/approval/list",
        form_fields_url="https://dev2.lanerp.com/api/field/formFields",
    )
    user = UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        authorization="Bearer test-token",
        uid="863",
    )

    template = service.get_template_detail("remote_5911", user)

    assert template.title == "测试外出"
    assert [field.name for field in template.fields] == [
        "go_out_start_time",
        "go_out_end_time",
        "go_out_addr",
        "go_out_content",
        "field_525823",
    ]
    assert [field.label for field in template.fields[:4]] == ["开始时间", "结束时间", "外出地点", "外出事由"]
    assert [field.type for field in template.fields] == ["date", "date", "text", "text", "text"]
    assert [field.required for field in template.fields] == [True, True, True, True, False]
    assert template.fields[0].question == "请选择开始时间"
    assert requests[1].headers["Authorization"] == "Bearer test-token"
    assert requests[1].headers["UID"] == "863"
    assert requests[1].content == b'{"field_form":"approval_type_5911"}'


def test_remote_approval_type_never_uses_local_mock_key() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.url.path == "/api/approval/list":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "message": "success",
                    "data": [
                        {
                            "id": 1371,
                            "name": "zh-测试",
                            "approvals": [
                                {
                                    "id": 6408,
                                    "name": "zh-请假",
                                    "type": "leave",
                                    "approval_type": "leave",
                                }
                            ],
                        }
                    ],
                },
            )
        if request.url.path == "/api/field/formFields":
            return httpx.Response(
                200,
                json={
                    "code": 200,
                    "message": "success",
                    "data": [
                        {
                            "field_key": "field_6408_text",
                            "field_name": "单行文本",
                            "field_type": "input",
                            "is_required": 1,
                            "sort": 1,
                            "extend": {"placeholder": "请输入"},
                        }
                    ],
                },
            )
        raise AssertionError(f"Unexpected request path: {request.url.path}")

    service = CrmApprovalService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        approval_list_url="https://dev2.lanerp.com/api/approval/list",
        form_fields_url="https://dev2.lanerp.com/api/field/formFields",
    )
    user = UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        authorization="Bearer test-token",
        uid="863",
    )

    templates = service.list_available_templates(user)
    template = service.get_template_detail(templates[0].approval_type, user)

    assert templates[0].approval_type == "remote_6408"
    assert template.approval_type == "remote_6408"
    assert [field.name for field in template.fields] == ["field_6408_text"]
    assert all(field.name != "leave_type" for field in template.fields)
    assert requests[-1].content == b'{"field_form":"approval_type_6408"}'


def test_get_nodes_parses_submitter_choice_assignees() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": [
                    {
                        "id": 12203,
                        "approval_set_id": 5904,
                        "type": "approval",
                        "name": "审批",
                        "level": 2,
                        "handle": {
                            "type": "submitter_self",
                            "is_single": 1,
                            "relate_user": [
                                {
                                    "uid": 863,
                                    "name": "桑东波",
                                    "display_name": "桑东波",
                                    "avatar": "https://example.com/a.jpg",
                                }
                            ],
                        },
                    },
                    {
                        "id": 12204,
                        "approval_set_id": 5904,
                        "type": "conduct",
                        "name": "办理",
                        "level": 3,
                        "handle": {
                            "type": "submitter_choice",
                            "is_single": 1,
                            "relate_user": [
                                {"uid": 864, "name": "张三", "display_name": "张三"},
                                {"uid": 865, "name": "李四", "display_name": "李四"},
                            ],
                        },
                    },
                ],
            },
        )

    service = CrmApprovalService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        get_nodes_url="https://dev2.lanerp.com/api/approval/getNodes",
    )
    user = UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        authorization="Bearer test-token",
        uid="863",
    )

    nodes = service.get_approval_nodes(
        approval_set_id="5904",
        form_value=[{"field_key": "rest_content", "value": "请假"}],
        user=user,
    )

    assert requests[0].headers["Authorization"] == "Bearer test-token"
    assert requests[0].headers["UID"] == "863"
    assert json.loads(requests[0].content) == {
        "approval_set_id": 5904,
        "form_value": [{"field_key": "rest_content", "value": "请假"}],
    }
    assert [node.node_id for node in nodes] == ["12203", "12204"]
    assert nodes[0].requires_selection is False
    assert nodes[0].selected_assignees[0].name == "桑东波"
    assert nodes[1].requires_selection is True
    assert nodes[1].multiple is False
    assert [user.name for user in nodes[1].candidate_assignees] == ["张三", "李四"]
    assert nodes[1].raw_node["approval_set_id"] == 5904
    assert nodes[1].raw_node["handle"]["type"] == "submitter_choice"


def test_remote_submit_posts_approval_add_payload() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {
                    "id": 9988,
                    "request_id": "AP202606100001",
                    "status": "待审批",
                },
            },
        )

    service = CrmApprovalService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        add_approval_url="https://dev2.lanerp.com/api/approval/add",
    )
    user = UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        authorization="Bearer test-token",
        uid="863",
    )
    nodes = [
        {
            "node_id": "12203",
            "node_name": "审批",
            "node_type": "approval",
            "level": 2,
            "handle_type": "submitter_self",
            "multiple": False,
            "requires_selection": False,
            "candidate_assignees": [{"uid": "863", "name": "桑东波", "avatar": None}],
            "selected_assignees": [{"uid": "863", "name": "桑东波", "avatar": None}],
            "raw_node": {
                "id": 12203,
                "pid": 12202,
                "approval_set_id": 5904,
                "type": "approval",
                "name": "审批",
                "level": 2,
                "allow_transfer": 1,
                "field_auth": [{"field_key": "rest_content", "field_auth": 2}],
            },
        },
        {
            "node_id": "12204",
            "node_name": "办理",
            "node_type": "conduct",
            "level": 3,
            "handle_type": "submitter_choice",
            "multiple": False,
            "requires_selection": True,
            "candidate_assignees": [{"uid": "864", "name": "张三", "avatar": None}],
            "selected_assignees": [],
            "raw_node": {
                "id": 12204,
                "pid": 12203,
                "approval_set_id": 5904,
                "type": "conduct",
                "name": "办理",
                "level": 3,
                "allow_return": 1,
                "field_auth": [{"field_key": "rest_content", "field_auth": 1}],
            },
        },
    ]

    result = service.submit_approval(
        "remote_5904",
        {"rest_content": "11111"},
        user,
        idempotency_key="ai-approval:test",
        approval_set_id="5904",
        approval_nodes=nodes,
        selected_assignees={"12204": ["864"]},
    )

    assert result.request_id == "AP202606100001"
    assert requests[0].headers["Authorization"] == "Bearer test-token"
    assert requests[0].headers["UID"] == "863"
    body = json.loads(requests[0].content)
    assert body["approval_set_id"] == 5904
    assert body["form_data"] == {"rest_content": {"value": "11111"}}
    assert body["node_list"][0]["pid"] == 12202
    assert body["node_list"][0]["field_auth"] == [{"field_key": "rest_content", "field_auth": 2}]
    assert body["node_list"][0]["handle_uids"] == [863]
    assert body["node_list"][1]["pid"] == 12203
    assert body["node_list"][1]["allow_return"] == 1
    assert body["node_list"][1]["field_auth"] == [{"field_key": "rest_content", "field_auth": 1}]
    assert body["node_list"][1]["handle_uids"] == [864]
    assert body["node_list"][1]["handle_uids_info"] == [{"uid": 864, "name": "张三", "avatar": None}]


def test_remote_submit_preserves_structured_form_data() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "code": 200,
                "message": "success",
                "data": {"id": 9988, "status": "待审批"},
            },
        )

    service = CrmApprovalService(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        add_approval_url="https://dev2.lanerp.com/api/approval/add",
    )
    user = UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        authorization="Bearer test-token",
        uid="863",
    )

    service.submit_approval(
        "remote_5904",
        {
            "rest_content": "11111",
            "rest_prove": [],
            "rest_rule_json": {"value": 13, "label": "事假"},
        },
        user,
        idempotency_key="ai-approval:test",
        approval_set_id="5904",
        approval_nodes=[],
        selected_assignees={},
    )

    body = json.loads(requests[0].content)
    assert body["form_data"] == {
        "rest_content": {"value": "11111"},
        "rest_prove": [],
        "rest_rule_json": {"value": 13, "label": "事假"},
    }

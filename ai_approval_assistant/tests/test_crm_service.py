from __future__ import annotations

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

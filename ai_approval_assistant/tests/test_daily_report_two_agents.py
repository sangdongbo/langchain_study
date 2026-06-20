from __future__ import annotations

import httpx

from app.agents.daily_report_chat_agent import daily_report_chat_agent_node
from app.agents.daily_report_form_agent import daily_report_form_agent_node
from app.graph.state import initial_state
from app.schemas.approval import UserContext
from app.schemas.daily_report import DailyReportContext, DailyReportSubmitResult
from app.services.daily_report_api_client import DailyReportApiClient


class FakeDailyReportService:
    def __init__(self) -> None:
        self.load_calls = 0
        self.submit_calls = 0
        self.context = DailyReportContext(
            report_type=1,
            report_date="2026-06-20",
            form_fields_payload={"code": 200, "data": []},
            config={"recipients": [{"relate_id": 959, "relate_name": "桑东波测试 2"}]},
            draft={},
            sync_data=[{"title": "客户跟进"}],
            default_payload={
                "type": 1,
                "date": "2026-06-20",
                "content": "",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959, "relate_name": "桑东波测试 2"}],
                "cc_recipients": [],
                "extends": {},
                "extend_fields": [],
            },
        )

    def load_context(self, user, report_type: int, report_date: str):
        self.load_calls += 1
        return self.context

    def payload_from_form_answer(self, answer):
        return answer["value"]

    def preview_from_payload(self, payload):
        return {
            "report_type": payload["type"],
            "date": payload["date"],
            "content": payload["content"],
            "fields": [],
            "recipients": payload.get("recipients", []),
            "cc_recipients": payload.get("cc_recipients", []),
            "sync_summary": "已同步 1 条数据",
        }

    def submit_payload(self, user, payload):
        self.submit_calls += 1
        return DailyReportSubmitResult(report_id="1001", status="success")


def test_daily_report_form_agent_returns_open_form_action(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_form_agent.daily_report_service", service)
    state = initial_state("S-form", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "写今天日报",
        }
    )

    result = daily_report_form_agent_node(state)

    assert service.load_calls == 1
    assert result["status"] == "awaiting_daily_report_form"
    assert result["ui_action"]["type"] == "open_daily_report_form"
    assert result["ui_action"]["payload"]["default_payload"]["type"] == 1
    assert result["ui_action"]["payload"]["sync_data"] == [{"title": "客户跟进"}]
    assert "daily_report_form_agent" in result["trace"]


def test_daily_report_form_agent_previews_frontend_form_answer(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_form_agent.daily_report_service", service)
    state = initial_state("S-form-answer", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "日报表单已填写",
            "_answer": {
                "field_key": "__daily_report_form__",
                "type": "daily_report_form",
                "value": {
                    "type": 1,
                    "date": "2026-06-20",
                    "content": "今天完成客户跟进",
                    "files": [],
                    "at_uids": [],
                    "recipients": [{"relate_id": 959}],
                    "cc_recipients": [],
                    "extends": {},
                    "extend_fields": [],
                },
            },
        }
    )

    result = daily_report_form_agent_node(state)

    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["daily_report_payload"]["content"] == "今天完成客户跟进"
    assert result["daily_report_preview"]["content"] == "今天完成客户跟进"
    assert "确认提交" in result["assistant_message"]


def test_daily_report_form_agent_preserves_frontend_custom_fields(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_form_agent.daily_report_service", service)
    state = initial_state("S-form-custom-fields", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "日报表单已填写",
            "_answer": {
                "field_key": "__daily_report_form__",
                "type": "daily_report_form",
                "value": {
                    "type": 1,
                    "date": "2026-06-20",
                    "content": "今天完成客户跟进",
                    "files": [],
                    "at_uids": [],
                    "recipients": [{"relate_id": 959}],
                    "cc_recipients": [],
                    "extends": {"custom_progress": {"value": "80%", "text": "80%"}},
                    "extend_fields": [
                        {"field": "custom_progress", "label": "完成进度", "type": "text"}
                    ],
                },
            },
        }
    )

    result = daily_report_form_agent_node(state)

    assert result["daily_report_payload"]["extends"] == {
        "custom_progress": {"value": "80%", "text": "80%"}
    }
    assert result["daily_report_payload"]["extend_fields"] == [
        {"field": "custom_progress", "label": "完成进度", "type": "text"}
    ]


def test_daily_report_form_agent_submits_confirmed_frontend_payload(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_form_agent.daily_report_service", service)
    state = initial_state("S-form-submit", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "确认提交",
            "status": "awaiting_daily_report_confirmation",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-20",
                "content": "今天完成客户跟进",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {},
                "extend_fields": [],
            },
        }
    )

    result = daily_report_form_agent_node(state)

    assert service.submit_calls == 1
    assert result["status"] == "daily_report_submitted"
    assert result["daily_report_request_id"] == "1001"


def test_daily_report_chat_agent_uses_message_content_as_fast_payload(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "今天完成客户跟进",
        }
    )

    result = daily_report_chat_agent_node(state)

    assert service.load_calls == 1
    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["daily_report_payload"]["content"] == "今天完成客户跟进"
    assert result["daily_report_preview"]["content"] == "今天完成客户跟进"
    assert "daily_report_chat_agent" in result["trace"]


def test_daily_report_api_client_sends_required_daily_report_requests() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "data": {}})

    client = DailyReportApiClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        base_url="https://dev3.lanerp.com",
    )
    user = UserContext(
        user_id="863",
        name="User 863",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid="863",
        authorization="Bearer token",
    )

    client.get_form_fields(user)
    client.get_config(user)
    client.get_draft(user, 1, "2026-06-20")
    client.sync_data(user, 1, "2026-06-20")
    client.add_daily_report(
        user,
        {
            "type": 1,
            "date": "2026-06-20",
            "content": "今天完成客户跟进",
            "files": [],
            "at_uids": [],
            "recipients": [{"relate_id": 959}],
            "cc_recipients": [],
            "extends": {"custom_progress": {"value": "80%", "text": "80%"}},
            "extend_fields": [
                {"field": "custom_progress", "label": "完成进度", "type": "text"}
            ],
        },
    )

    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/api/field/formFields"),
        ("GET", "/oa/dailyReport/config/get"),
        ("GET", "/oa/dailyReport/draft/get"),
        ("POST", "/api/oa/dailyReport/syncData"),
        ("POST", "/oa/dailyReport/add"),
    ]
    assert requests[0].read() == b'{"field_form":"daily_reports"}'
    assert requests[1].url.params["need_parse"] == "1"
    assert requests[2].url.params["type"] == "1"
    assert requests[2].url.params["date"] == "2026-06-20"
    assert requests[3].read() == (
        b'{"daily_report_type":1,"sync_type":["process","followup","order",'
        b'"work_ticket","customer_manage"],"date_range":["2026-06-20","2026-06-20"]}'
    )
    assert b'"extends":{"custom_progress":{"value":"80%","text":"80%"}}' in requests[4].read()

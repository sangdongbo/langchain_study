from __future__ import annotations

import httpx
import json

from app.agents.daily_report.action_agent import DailyReportActionAgent
from app.agents.daily_report_chat_agent import daily_report_chat_agent_node
from app.graph.state import initial_state
from app.schemas.approval import UserContext
from app.schemas.daily_report import DailyReportContext, DailyReportSubmitResult
from app.services.daily_report_api_client import DailyReportApiClient
from app.services.daily_report_service import DailyReportService, DailyReportSubmitError
from app.services.session_state_service import session_state_service


FORM_FIELDS = [
    {
        "field_key": "content",
        "field_name": "工作内容",
        "field_type": "textarea",
        "is_system": 1,
        "is_required": 1,
    },
    {
        "field_key": "field_513687",
        "field_name": "单行文本",
        "field_type": "input",
        "is_system": 0,
        "is_required": 0,
    },
    {
        "field_key": "field_513692",
        "field_name": "单选",
        "field_type": "radio",
        "is_system": 0,
        "is_required": 0,
        "extend": {
            "options": [
                {"label": "单选1", "value": 1, "default": False},
                {"label": "单选2", "value": 2, "default": False},
            ]
        },
    },
]


def test_daily_report_action_agent_prefers_structured_actions() -> None:
    agent = DailyReportActionAgent()
    state = initial_state("S-daily-action-structured", "863")
    state.update(
        {
            "status": "awaiting_daily_report_confirmation",
            "user_message": "随便说点别的",
            "_answer": {
                "field_key": "action",
                "label": "修改日期",
                "value": "modify_date",
            },
        }
    )

    result = agent.classify(state)

    assert result.action == "edit_date"
    assert result.route == "collect_date"
    assert result.source == "answer"


def test_daily_report_action_agent_classifies_text_actions() -> None:
    agent = DailyReportActionAgent()
    state = initial_state("S-daily-action-text", "863")
    state.update(
        {
            "status": "awaiting_daily_report_confirmation",
            "user_message": "我想改一下日志日期",
        }
    )

    result = agent.classify(state)

    assert result.action == "edit_date"
    assert result.route == "collect_date"
    assert result.source in {"llm", "rule"}


REAL_ADD_PAYLOAD = {
    "type": 1,
    "date": "2026-06-22",
    "content": "<div class=\"other_content\">123123</div>",
    "files": [],
    "at_uids": [],
    "recipients": [
        {
            "relate_type_id": "959_App\\Models\\User",
            "relate_id": 959,
            "relate_name": "桑东波测试 2",
            "relate_type": "App\\Models\\User",
            "relate_avatar": None,
        }
    ],
    "cc_recipients": [],
    "extends": {
        "field_513687": {"value": "1122"},
        "field_513692": {"value": None, "text": None},
        "field_514141": {"value": "22"},
        "field_514663": {"value": []},
        "field_514664": {"value": []},
    },
    "extend_fields": [
        {
            "field_id": 513687,
            "company_id": 16,
            "field_form": "daily_reports",
            "field_key": "field_513687",
            "field_name": "单行文本",
            "field_type": "input",
            "p_field_key": "",
            "quote_field_form": "",
            "quote_field_key": "",
            "is_system": 0,
            "is_system_key": 0,
            "is_reset": 0,
            "is_unique": 0,
            "is_required": 0,
            "extend": {"col_span": 12, "input_type": "text", "placeholder": "请输入"},
            "rules": [],
            "status": 0,
            "sort": 2,
        },
        {
            "field_id": 513692,
            "company_id": 16,
            "field_form": "daily_reports",
            "field_key": "field_513692",
            "field_name": "单选",
            "field_type": "radio",
            "p_field_key": "",
            "quote_field_form": "",
            "quote_field_key": "",
            "is_system": 0,
            "is_system_key": 0,
            "is_reset": 0,
            "is_unique": 0,
            "is_required": 0,
            "extend": {
                "options": [
                    {"label": "单选1", "value": 1, "default": False},
                    {"label": "单选2", "value": 2, "default": False},
                ],
                "col_span": 12,
                "placeholder": "请选择",
                "tag_interaction": False,
                "max_option_value": 3,
            },
            "rules": [],
            "status": 0,
            "sort": 3,
        },
        {
            "field_id": 514141,
            "company_id": 16,
            "field_form": "daily_reports",
            "field_key": "field_514141",
            "field_name": "多行文本",
            "field_type": "textarea",
            "p_field_key": "",
            "quote_field_form": "",
            "quote_field_key": "",
            "is_system": 0,
            "is_system_key": 0,
            "is_reset": 0,
            "is_unique": 0,
            "is_required": 0,
            "extend": {"col_span": 24, "placeholder": "请输入"},
            "rules": [],
            "status": 0,
            "sort": 4,
        },
        {
            "field_id": 514663,
            "company_id": 16,
            "field_form": "daily_reports",
            "field_key": "field_514663",
            "field_name": "关联审批单",
            "field_type": "checkbox_approval",
            "p_field_key": "",
            "quote_field_form": "",
            "quote_field_key": "",
            "is_system": 0,
            "is_system_key": 0,
            "is_reset": 0,
            "is_unique": 0,
            "is_required": 0,
            "extend": {
                "col_span": 24,
                "optional_range": False,
                "relate_approved": False,
                "not_promoter_self": True,
                "approve_form_scope": [],
                "self_in_approval_process_node": True,
            },
            "rules": [],
            "status": 0,
            "sort": 5,
        },
        {
            "field_id": 514664,
            "company_id": 16,
            "field_form": "daily_reports",
            "field_key": "field_514664",
            "field_name": "关联打卡记录",
            "field_type": "checkbox_check_record",
            "p_field_key": "",
            "quote_field_form": "",
            "quote_field_key": "",
            "is_system": 0,
            "is_system_key": 0,
            "is_reset": 0,
            "is_unique": 0,
            "is_required": 0,
            "extend": {
                "col_span": 24,
                "addition_of_multiple": True,
                "mobile_devices_directly": False,
            },
            "rules": [],
            "status": 0,
            "sort": 6,
        },
    ],
}


class FakeDailyReportService:
    def __init__(self) -> None:
        self.load_calls = 0
        self.submit_calls = 0
        self.saved_drafts = []
        self.context = DailyReportContext(
            report_type=1,
            report_date="2026-06-22",
            form_fields_payload={"code": 200, "data": FORM_FIELDS},
            config={},
            draft={
                "type": 1,
                "date": "2026-06-22",
                "content": "<div class=\"other_content\">123123</div>",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959, "relate_name": "桑东波测试 2"}],
                "cc_recipients": [],
                "extends": {
                    "field_513687": {"value": "1122"},
                    "field_513692": {"value": None, "text": None},
                },
            },
            sync_data=[{"title": "客户跟进"}],
            default_payload={
                "type": 1,
                "date": "2026-06-22",
                "content": "<div class=\"other_content\">123123</div>",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959, "relate_name": "桑东波测试 2"}],
                "cc_recipients": [],
                "extends": {
                    "field_513687": {"value": "1122"},
                    "field_513692": {"value": None, "text": None},
                },
                "extend_fields": [field for field in FORM_FIELDS if field["field_key"] != "content"],
            },
        )

    def load_context(self, user, report_type: int, report_date: str):
        self.load_calls += 1
        return self.context

    def preview_from_payload(self, payload):
        return {
            "report_type": payload["type"],
            "date": payload["date"],
            "content": payload["content"],
            "fields": [
                {
                    "name": "field_513687",
                    "label": "单行文本",
                    "value": "1122",
                }
            ],
            "recipients": payload.get("recipients", []),
            "cc_recipients": payload.get("cc_recipients", []),
            "sync_summary": "已同步 1 条数据",
        }

    def save_draft_payload(self, user, payload):
        self.saved_drafts.append(payload)
        return {"code": 200, "data": ""}

    def submit_payload(self, user, payload):
        self.submit_calls += 1
        return DailyReportSubmitResult(report_id="1001", status="success")


class FailingDailyReportService(FakeDailyReportService):
    def submit_payload(self, user, payload):
        self.submit_calls += 1
        raise DailyReportSubmitError("请填写汇报人")


def test_daily_report_chat_agent_is_available_through_chat_api(monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from app.main import app
    from app.graph.workflow import get_workflow

    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    get_workflow.cache_clear()
    session_state_service.clear("S-daily-chat-api")

    response = TestClient(app).post(
        "/api/ai-approval/chat",
        json={
            "session_id": "S-daily-chat-api",
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer test-token",
            "message": "写日报",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "awaiting_daily_report_confirmation"
    assert body["daily_report_payload"]["content"] == "<div class=\"other_content\">123123</div>"
    assert body["daily_report_payload"]["recipients"] == [
        {"relate_id": 959, "relate_name": "桑东波测试 2"}
    ]
    assert body["daily_report_payload"]["extend_fields"] == [
        field for field in FORM_FIELDS if field["field_key"] != "content"
    ]
    assert "daily_report_chat_agent" in body["trace"]


def test_daily_report_chat_agent_loads_draft_and_custom_fields(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "写今天日报",
        }
    )

    result = daily_report_chat_agent_node(state)

    assert service.load_calls == 1
    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["daily_report_payload"]["content"] == "<div class=\"other_content\">123123</div>"
    assert result["daily_report_payload"]["extends"] == {
        "field_513687": {"value": "1122"},
        "field_513692": {"value": None, "text": None},
    }
    assert result["daily_report_preview"]["recipients"] == [
        {"relate_id": 959, "relate_name": "桑东波测试 2"}
    ]
    assert "确认提交" in result["assistant_message"]


def test_daily_report_chat_agent_confirmation_message_is_readable(monkeypatch) -> None:
    api_client = FakeApiClient()
    api_client.draft["content"] = '<div class="other_content">11112222</div>'
    api_client.draft["extends"] = {
        "field_513687": {"value": "1122"},
        "field_513692": {"value": None, "text": None},
        "field_514141": {"value": ""},
    }
    service = DailyReportService(api_client=api_client)
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-readable-confirmation", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "写日报",
        }
    )

    result = daily_report_chat_agent_node(state)

    assert "工作内容：11112222" in result["assistant_message"]
    assert '<div class="other_content">' not in result["assistant_message"]
    assert "单行文本：1122" in result["assistant_message"]
    assert "field_513687" not in result["assistant_message"]
    assert "field_513692" not in result["assistant_message"]
    assert "field_514141" not in result["assistant_message"]
    assert result["ui_action"] == {
        "type": "interrupt",
        "field_key": "daily_report_confirmation",
        "label": "确认提交",
        "input_type": "action",
        "required": True,
        "value": None,
        "message": result["assistant_message"],
        "actions": ["confirm", "modify", "modify_date", "cancel"],
    }


def test_daily_report_chat_agent_uses_user_content_when_provided(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-user-content", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "写日报：今天完成客户跟进",
        }
    )

    result = daily_report_chat_agent_node(state)

    assert result["daily_report_payload"]["content"] == "今天完成客户跟进"
    assert result["daily_report_preview"]["content"] == "今天完成客户跟进"
    assert service.saved_drafts[-1]["content"] == "今天完成客户跟进"


def test_daily_report_chat_agent_asks_for_content_when_payload_content_is_empty(monkeypatch) -> None:
    service = FakeDailyReportService()
    service.context.default_payload["content"] = ""
    service.context.draft["content"] = ""
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-empty-content", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "写日志",
        }
    )

    result = daily_report_chat_agent_node(state)

    assert result["status"] == "collecting"
    assert result["awaiting_field"] == "daily_report_content"
    assert result["assistant_message"] == "今天还没有可提交的工作内容，请补充日志的工作内容。"
    assert result["daily_report_payload"]["content"] == ""
    assert result["ui_action"] == {
        "type": "interrupt",
        "field_key": "daily_report_content",
        "label": "工作内容",
        "input_type": "textarea",
        "required": True,
        "value": "",
        "message": "今天还没有可提交的工作内容，请补充日志的工作内容。",
    }
    assert "daily_report_chat_agent" in result["trace"]


def test_daily_report_chat_agent_uses_followup_content_after_empty_payload(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-followup-content", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "今天完成客户跟进",
            "status": "collecting",
            "awaiting_field": "daily_report_content",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {"field_513687": {"value": "1122"}},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["awaiting_field"] is None
    assert result["daily_report_payload"]["content"] == "今天完成客户跟进"
    assert result["daily_report_preview"]["content"] == "今天完成客户跟进"
    assert service.saved_drafts[-1]["content"] == "今天完成客户跟进"


def test_daily_report_chat_agent_uses_structured_followup_content(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-followup-structured-content", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "提交",
            "_answer": {
                "field_key": "daily_report_content",
                "type": "textarea",
                "label": "修改后的工作内容",
                "value": "修改后的工作内容",
            },
            "status": "collecting",
            "awaiting_field": "daily_report_content",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "用户之前填写的日志内容",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {"field_513687": {"value": "1122"}},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["awaiting_field"] is None
    assert result["daily_report_payload"]["content"] == "修改后的工作内容"
    assert result["daily_report_preview"]["content"] == "修改后的工作内容"
    assert service.saved_drafts[-1]["content"] == "修改后的工作内容"


def test_daily_report_chat_agent_modifies_content_before_confirmation(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-modify-content", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "工作内容改成今天完成客户拜访，并整理跟进记录",
            "status": "awaiting_daily_report_confirmation",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "原来的内容",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {"field_513687": {"value": "1122"}},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert service.submit_calls == 0
    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["daily_report_payload"]["content"] == "今天完成客户拜访，并整理跟进记录"
    assert result["daily_report_preview"]["content"] == "今天完成客户拜访，并整理跟进记录"
    assert service.saved_drafts[-1]["content"] == "今天完成客户拜访，并整理跟进记录"
    assert "今天完成客户拜访，并整理跟进记录" in result["assistant_message"]


def test_daily_report_chat_agent_modifies_structured_content_before_confirmation(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-modify-structured-content", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "修改工作内容",
            "_answer": {
                "field_key": "daily_report_content",
                "type": "textarea",
                "label": "今天完成客户拜访",
                "value": "今天完成客户拜访",
            },
            "status": "awaiting_daily_report_confirmation",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "原来的内容",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert service.submit_calls == 0
    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["daily_report_payload"]["content"] == "今天完成客户拜访"
    assert service.saved_drafts[-1]["content"] == "今天完成客户拜访"


def test_daily_report_chat_agent_reopens_content_editor_from_confirmation(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-reopen-content-editor", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "修改",
            "_answer": {
                "field_key": "action",
                "type": "single_select",
                "label": "修改",
                "value": "modify",
            },
            "status": "awaiting_daily_report_confirmation",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "用户之前填写的日志内容",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {"field_513687": {"value": "1122"}},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert result["status"] == "collecting"
    assert result["awaiting_field"] == "daily_report_content"
    assert result["daily_report_payload"]["content"] == "用户之前填写的日志内容"
    assert result["assistant_message"] == "请修改日志的工作内容，提交后我会重新给你确认。"


def test_daily_report_chat_agent_reopens_date_editor_from_confirmation(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-reopen-date-editor", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "修改日期",
            "_answer": {
                "field_key": "action",
                "type": "single_select",
                "label": "修改日期",
                "value": "modify_date",
            },
            "status": "awaiting_daily_report_confirmation",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "用户之前填写的日志内容",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {"field_513687": {"value": "1122"}},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert result["status"] == "collecting"
    assert result["awaiting_field"] == "daily_report_date"
    assert result["daily_report_date"] == "2026-06-22"
    assert result["assistant_message"] == "请选择要填写日报的日期，我会重新获取当天草稿。"
    assert result["ui_action"] == {
        "type": "interrupt",
        "field_key": "daily_report_date",
        "label": "日志时间",
        "input_type": "date",
        "required": True,
        "value": "2026-06-22",
        "message": "请选择要填写日报的日期，我会重新获取当天草稿。",
    }


def test_daily_report_chat_agent_reloads_context_after_date_change(monkeypatch) -> None:
    service = FakeDailyReportService()
    service.context.default_payload["date"] = "2026-06-21"
    service.context.default_payload["content"] = "新日期的草稿内容"
    service.context.report_date = "2026-06-21"
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-date-change", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "提交",
            "_answer": {
                "field_key": "daily_report_date",
                "type": "date",
                "label": "2026-06-21",
                "value": "2026-06-21",
            },
            "status": "collecting",
            "awaiting_field": "daily_report_date",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "旧日期的草稿内容",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {"field_513687": {"value": "1122"}},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert service.load_calls == 1
    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["awaiting_field"] is None
    assert result["daily_report_date"] == "2026-06-21"
    assert result["daily_report_payload"]["date"] == "2026-06-21"
    assert result["daily_report_payload"]["content"] == "新日期的草稿内容"
    assert result["daily_report_preview"]["date"] == "2026-06-21"


def test_daily_report_chat_agent_submits_confirmed_payload(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-submit", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "确认提交",
            "status": "awaiting_daily_report_confirmation",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "<div class=\"other_content\">123123</div>",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {"field_513687": {"value": "1122"}},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert service.submit_calls == 1
    assert result["status"] == "daily_report_submitted"
    assert result["daily_report_request_id"] == "1001"


def test_daily_report_chat_agent_cancels_from_confirmation(monkeypatch) -> None:
    service = FakeDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-cancel-daily-report", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "取消",
            "_answer": {"field_key": "action", "value": "cancel", "label": "取消"},
            "status": "awaiting_daily_report_confirmation",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "<div class=\"other_content\">123123</div>",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
                "extends": {"field_513687": {"value": "1122"}},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert result["status"] == "cancelled"
    assert result["awaiting_field"] is None
    assert result["assistant_message"] == "已取消本次日报提交。"
    assert result["ui_action"] is None
    assert service.submit_calls == 0


def test_daily_report_chat_agent_returns_error_when_submit_is_rejected(monkeypatch) -> None:
    service = FailingDailyReportService()
    monkeypatch.setattr("app.agents.daily_report_chat_agent.daily_report_service", service)
    state = initial_state("S-chat-submit-rejected", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "确认",
            "status": "awaiting_daily_report_confirmation",
            "daily_report_payload": {
                "type": 1,
                "date": "2026-06-22",
                "content": "111222333",
                "files": [],
                "at_uids": [],
                "recipients": [],
                "cc_recipients": [],
                "extends": {},
                "extend_fields": [FORM_FIELDS[1]],
            },
        }
    )

    result = daily_report_chat_agent_node(state)

    assert service.submit_calls == 1
    assert result["status"] == "error"
    assert result["assistant_message"] == "日报提交失败：请填写汇报人"
    assert result["field_errors"] == [{"field": "daily_report", "message": "请填写汇报人"}]


def test_daily_report_service_excludes_system_content_from_extend_fields() -> None:
    service = DailyReportService(api_client=FakeApiClient())
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

    context = service.load_context(user, 1, "2026-06-22")

    assert context.default_payload["content"] == "<div class=\"other_content\">123123</div>"
    assert context.default_payload["recipients"] == [
        {"relate_id": 959, "relate_name": "桑东波测试 2"}
    ]
    assert context.default_payload["extends"] == {
        "field_513687": {"value": "1122"},
        "field_513692": {"value": None, "text": None},
    }
    assert context.default_payload["extend_fields"] == [
        field for field in FORM_FIELDS if field["field_key"] != "content"
    ]


def test_daily_report_service_sets_draft_from_config_when_draft_has_no_recipients() -> None:
    api_client = FakeApiClient()
    api_client.draft = {
        "type": 1,
        "date": "2026-06-22",
        "content": "",
        "files": [],
        "at_uids": [],
        "recipients": [],
        "cc_recipients": [],
        "extends": {},
    }
    api_client.config = {
        "parse_recipients": [
            {
                "relate_type_id": "959_App\\Models\\User",
                "relate_id": 959,
                "relate_name": "桑东波测试 2",
                "relate_type": "App\\Models\\User",
                "relate_avatar": None,
            }
        ],
        "parse_cc_recipients": [],
    }
    service = DailyReportService(api_client=api_client)
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

    context = service.load_context(user, 1, "2026-06-22")

    assert api_client.draft_get_calls == [(1, "2026-06-22"), (1, "2026-06-22")]
    assert api_client.draft_set_payloads == [
        {
            "data": {
                "type": 1,
                "date": "2026-06-22",
                "recipients": [
                    {
                        "relate_type_id": "959_App\\Models\\User",
                        "relate_id": 959,
                        "relate_name": "桑东波测试 2",
                        "relate_type": "App\\Models\\User",
                        "relate_avatar": None,
                    }
                ],
                "cc_recipients": [],
            }
        }
    ]
    assert context.default_payload["recipients"] == [
        {
            "relate_type_id": "959_App\\Models\\User",
            "relate_id": 959,
            "relate_name": "桑东波测试 2",
            "relate_type": "App\\Models\\User",
            "relate_avatar": None,
        }
    ]


def test_daily_report_service_uses_config_recipients_when_draft_set_does_not_echo_them() -> None:
    api_client = FakeApiClient()
    api_client.echo_set_draft = False
    api_client.draft = {
        "type": 1,
        "date": "2026-06-22",
        "content": "",
        "files": [],
        "at_uids": [],
        "recipients": [],
        "cc_recipients": [],
        "extends": {},
    }
    api_client.config = {
        "parse_recipients": [{"relate_id": 959, "relate_name": "桑东波测试 2"}],
        "parse_cc_recipients": [{"relate_id": 960, "relate_name": "抄送人"}],
    }
    service = DailyReportService(api_client=api_client)
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

    context = service.load_context(user, 1, "2026-06-22")

    assert context.default_payload["recipients"] == [
        {"relate_id": 959, "relate_name": "桑东波测试 2"}
    ]
    assert context.default_payload["cc_recipients"] == [
        {"relate_id": 960, "relate_name": "抄送人"}
    ]


def test_daily_report_service_does_not_set_draft_when_draft_already_has_recipients() -> None:
    api_client = FakeApiClient()
    service = DailyReportService(api_client=api_client)
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

    service.load_context(user, 1, "2026-06-22")

    assert api_client.draft_get_calls == [(1, "2026-06-22")]
    assert api_client.draft_set_payloads == []


def test_daily_report_service_uses_sync_data_when_draft_content_is_empty() -> None:
    api_client = FakeApiClient()
    api_client.draft = {
        "type": 1,
        "date": "2026-06-22",
        "content": "",
        "files": [],
        "at_uids": [],
        "recipients": [{"relate_id": 959, "relate_name": "桑东波测试 2"}],
        "cc_recipients": [],
        "extends": {},
    }
    api_client.sync_payload = [
        {"title": "跟进客户A并更新商机"},
        {"content": "处理工单#1001"},
    ]
    service = DailyReportService(api_client=api_client)
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

    context = service.load_context(user, 1, "2026-06-22")

    assert "跟进客户A并更新商机" in context.default_payload["content"]
    assert "处理工单#1001" in context.default_payload["content"]


def test_daily_report_service_saves_full_draft_payload() -> None:
    api_client = FakeApiClient()
    service = DailyReportService(api_client=api_client)
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
    payload = {
        "type": 1,
        "date": "2026-06-22",
        "content": "今天完成客户跟进",
        "files": [],
        "at_uids": [],
        "recipients": [{"relate_id": 959}],
        "cc_recipients": [],
        "extends": {"field_513687": {"value": "1122"}},
        "extend_fields": [FORM_FIELDS[1]],
    }

    service.save_draft_payload(user, payload)

    assert api_client.draft_set_payloads[-1] == {
        "data": {
            "type": 1,
            "date": "2026-06-22",
            "content": "今天完成客户跟进",
            "files": [],
            "at_uids": [],
            "recipients": [{"relate_id": 959}],
            "cc_recipients": [],
            "extends": {"field_513687": {"value": "1122"}},
        }
    }


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
    client.get_draft(user, 1, "2026-06-22")
    client.set_draft(
        user,
        {
            "data": {
                "type": 1,
                "date": "2026-06-22",
                "recipients": [{"relate_id": 959}],
                "cc_recipients": [],
            }
        },
    )
    client.sync_data(user, 1, "2026-06-22")
    client.add_daily_report(
        user,
        {
            "type": 1,
            "date": "2026-06-22",
            "content": "<div class=\"other_content\">123123</div>",
            "files": [],
            "at_uids": [],
            "recipients": [{"relate_id": 959}],
            "cc_recipients": [],
            "extends": {"field_513687": {"value": "1122"}},
            "extend_fields": [FORM_FIELDS[1]],
        },
    )

    assert [(request.method, request.url.path) for request in requests] == [
        ("POST", "/api/field/formFields"),
        ("GET", "/oa/dailyReport/config/get"),
        ("GET", "/oa/dailyReport/draft/get"),
        ("POST", "/oa/dailyReport/config/draft/set"),
        ("POST", "/api/oa/dailyReport/syncData"),
        ("POST", "/oa/dailyReport/add"),
    ]
    assert requests[0].read() == b'{"field_form":"daily_reports"}'
    assert requests[1].url.params["need_parse"] == "1"
    assert requests[2].url.params["type"] == "1"
    assert requests[2].url.params["date"] == "2026-06-22"
    assert requests[3].read() == (
        b'{"data":{"type":1,"date":"2026-06-22","recipients":[{"relate_id":959}],'
        b'"cc_recipients":[]}}'
    )
    assert requests[4].read() == (
        b'{"daily_report_type":1,"sync_type":["process","followup","order",'
        b'"work_ticket","customer_manage"],"date_range":["2026-06-22","2026-06-22"]}'
    )
    assert b'"extends":{"field_513687":{"value":"1122"}}' in requests[5].read()


def test_daily_report_api_client_posts_real_add_payload_unchanged() -> None:
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={"code": 200, "data": {"id": 1001}})

    client = DailyReportApiClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
        base_url="http://127.0.0.1:8002",
    )
    user = UserContext(
        user_id="863",
        name="桑东波",
        company_id="16",
        dept_id="",
        role="",
        manager_id="",
        uid="863",
        authorization="Bearer token",
    )

    response = client.add_daily_report(user, REAL_ADD_PAYLOAD)

    assert response == {"code": 200, "data": {"id": 1001}}
    assert requests[0].method == "POST"
    assert str(requests[0].url) == "http://127.0.0.1:8002/oa/dailyReport/add"
    assert requests[0].headers["Authorization"] == "Bearer token"
    assert requests[0].headers["UID"] == "863"
    assert requests[0].read().decode("utf-8") == json.dumps(
        REAL_ADD_PAYLOAD, ensure_ascii=False, separators=(",", ":")
    )


def test_daily_report_api_client_uses_crm_base_url_from_env(monkeypatch) -> None:
    captured_urls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured_urls.append(str(request.url))
        return httpx.Response(200, json={"code": 200, "data": {}})

    monkeypatch.setenv("AI_APPROVAL_CRM_BASE_URL", "http://127.0.0.1:8002")
    client = DailyReportApiClient(
        http_client=httpx.Client(transport=httpx.MockTransport(handler))
    )
    user = UserContext(
        user_id="863",
        name="桑东波",
        company_id="16",
        dept_id="",
        role="",
        manager_id="",
        uid="863",
        authorization="Bearer token",
    )

    client.get_config(user)

    assert captured_urls == [
        "http://127.0.0.1:8002/oa/dailyReport/config/get?need_parse=1"
    ]


class FakeApiClient:
    def __init__(self) -> None:
        self.draft_get_calls = []
        self.draft_set_payloads = []
        self.echo_set_draft = True
        self.config = {}
        self.sync_payload = [{"title": "客户跟进"}]
        self.draft = {
            "type": 1,
            "date": "2026-06-22",
            "content": "<div class=\"other_content\">123123</div>",
            "files": [],
            "at_uids": [],
            "recipients": [{"relate_id": 959, "relate_name": "桑东波测试 2"}],
            "cc_recipients": [],
            "extends": {
                "field_513687": {"value": "1122"},
                "field_513692": {"value": None, "text": None},
            },
        }

    def get_form_fields(self, user):
        return {"code": 200, "data": FORM_FIELDS}

    def get_config(self, user):
        return {"code": 200, "data": self.config}

    def get_draft(self, user, report_type: int, report_date: str):
        self.draft_get_calls.append((report_type, report_date))
        return {"code": 200, "data": self.draft}

    def set_draft(self, user, payload):
        self.draft_set_payloads.append(payload)
        if self.echo_set_draft:
            self.draft = {
                **self.draft,
                **payload.get("data", {}),
            }
        return {"code": 200, "data": ""}

    def sync_data(self, user, report_type: int, report_date: str):
        return {"code": 200, "data": self.sync_payload}

    def add_daily_report(self, user, payload):
        return {"code": 200, "data": {"id": 1001, "status": "success"}}

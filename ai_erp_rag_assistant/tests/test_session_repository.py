from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ai_erp_rag_assistant.app.api import session_list, session_messages
from ai_erp_rag_assistant.app.schemas import SessionListRequest, SessionMessagesRequest
from ai_erp_rag_assistant.app.services.session_repository import (
    SessionRepository,
    resumable_state,
)


def test_resumable_state_keeps_workflow_and_removes_credentials():
    snapshot = resumable_state(
        {
            "authorization": "Bearer secret",
            "uid": "863",
            "template": {"template_id": "5904"},
            "fields": {"reason": "就医"},
            "preview": {
                "preview_id": "preview-1",
                "nested": {"token": "secret-token"},
            },
            "workflow_status": "preview_ready",
            "active_approval": True,
            "user_context": {
                "company_id": "16",
                "authorization": "Bearer secret",
                "raw_userinfo": {"private": "value"},
            },
        }
    )

    assert snapshot["template"]["template_id"] == "5904"
    assert snapshot["fields"] == {"reason": "就医"}
    assert snapshot["preview"]["nested"] == {}
    assert snapshot["workflow_status"] == "preview_ready"
    assert "authorization" not in snapshot
    assert "user_context" not in snapshot


class _Cursor:
    def __init__(self):
        self.queries: list[tuple[str, tuple | None]] = []
        self.lastrowid = 10
        self._row = None

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        if params is not None:
            assert compact.count("%s") == len(params)
        self.queries.append((compact, params))
        if "SELECT id, published_config_version_id" in compact:
            self._row = {"id": 2, "published_config_version_id": 3}
        elif "SELECT id, last_message_seq" in compact:
            self._row = None
        elif "SELECT id FROM ai_erp_messages" in compact:
            self._row = None
        elif "SELECT id FROM ai_erp_approval_drafts" in compact:
            self._row = {"id": 20}
        else:
            self._row = None

    def fetchone(self):
        return self._row


class _Connection:
    def __init__(self):
        self.cursor_instance = _Cursor()
        self.committed = False
        self.rolled_back = False

    def cursor(self):
        return self.cursor_instance

    def commit(self):
        self.committed = True

    def rollback(self):
        self.rolled_back = True

    def close(self):
        pass


class _ReadCursor:
    def __init__(self):
        self.queries: list[tuple[str, tuple | None]] = []
        self._rows: list[dict] = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        if params is not None:
            assert compact.count("%s") == len(params)
        self.queries.append((compact, params))
        if "SELECT s.session_key AS session_id" in compact:
            self._rows = [
                {"session_id": "session-3"},
                {"session_id": "session-2"},
                {"session_id": "session-1"},
            ]
        else:
            self._rows = [
                {
                    "message_seq": 5,
                    "role": "assistant",
                    "content": "回复",
                    "metadata_json": {"response": {"preview": {"preview_id": "p-1"}}},
                },
                {"message_seq": 4, "role": "user", "content": "问题"},
                {"message_seq": 3, "role": "assistant", "content": "更早回复"},
            ]

    def fetchall(self):
        return self._rows


class _ReadConnection:
    def __init__(self):
        self.cursor_instance = _ReadCursor()

    def cursor(self):
        return self.cursor_instance

    def close(self):
        pass


def test_save_exchange_persists_session_approval_and_audit_without_real_database(monkeypatch):
    connection = _Connection()
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.session_repository.get_settings",
        lambda: SimpleNamespace(session_store="mysql"),
    )
    monkeypatch.setattr(SessionRepository, "_connect", staticmethod(lambda: connection))
    repository = SessionRepository()
    preview = {
        "preview_id": "a" * 32,
        "preview_version": 1,
        "preview_hash": "b" * 64,
        "template_id": "5904",
        "title": "请假",
        "submission_fields": {"reason": "就医"},
        "nodes": [],
        "submit_nodes": [],
        "approval_flow": [],
        "requires_confirmation": True,
        "idempotency_key": "idem-1",
    }

    repository.save_exchange(
        company_id="16",
        assistant_key="erp-rag",
        session_key="session-1",
        user_id="863",
        erp_uid="863",
        request_id="request-1",
        user_message="明天下午请病假",
        state={
            "draft_key": "draft-1",
            "template": {"template_id": "5904", "title": "请假"},
            "fields": {"reason": "就医"},
            "selected_assignees": {},
            "preview": preview,
            "erp_data": {
                "idempotency_key": "idem-1",
                "approval_id": "approval-1",
                "template_code": "5904",
                "erp_mode": "remote",
                "erp_write_mode": "remote",
            },
            "workflow_status": "preview_ready",
            "active_approval": True,
            "route": "approval_workflow",
            "authorization": "Bearer secret",
        },
        response={
            "message": "请确认",
            "tool_calls": [{"tool": "erp.validate_fields", "fields": {"reason": "就医"}}],
        },
    )

    sql = "\n".join(query for query, _ in connection.cursor_instance.queries)
    params_text = repr([params for _, params in connection.cursor_instance.queries])
    assert connection.committed is True
    assert "INSERT INTO ai_erp_sessions" in sql
    assert "INSERT INTO ai_erp_approval_drafts" in sql
    assert "INSERT INTO ai_erp_approval_previews" in sql
    assert "INSERT INTO ai_erp_tool_events" in sql
    assert "Bearer secret" not in params_text
    submission = next(
        params
        for query, params in connection.cursor_instance.queries
        if "INSERT INTO ai_erp_submission_attempts" in query
    )
    assert submission[7] == "request-1"


def test_session_repository_scopes_and_pages_reads_without_real_database(monkeypatch):
    connection = _ReadConnection()
    monkeypatch.setattr(SessionRepository, "_connect", staticmethod(lambda: connection))
    repository = SessionRepository()

    sessions, more_sessions = repository.list_sessions(
        company_id="16",
        assistant_key="erp-rag",
        user_id="863",
        status="active",
        page=2,
        page_size=2,
    )
    messages, more_messages = repository.list_messages(
        company_id="16",
        assistant_key="erp-rag",
        user_id="863",
        session_key="session-3",
        before_seq=6,
        page_size=2,
    )

    assert [item["session_id"] for item in sessions] == ["session-3", "session-2"]
    assert more_sessions is True
    assert [item["message_seq"] for item in messages] == [4, 5]
    assert messages[1]["response"]["preview"]["preview_id"] == "p-1"
    assert more_messages is True
    assert connection.cursor_instance.queries[0][1] == (
        "16",
        "erp-rag",
        "863",
        "active",
        3,
        2,
    )
    assert connection.cursor_instance.queries[1][1] == (
        "16",
        "erp-rag",
        "863",
        "session-3",
        6,
        6,
        3,
    )


def test_session_read_apis_use_verified_owner_and_pagination(monkeypatch):
    calls = {}

    class Repository:
        enabled = True

        @staticmethod
        def list_sessions(**kwargs):
            calls["sessions"] = kwargs
            return [{"session_id": "session-1"}], False

        @staticmethod
        def list_messages(**kwargs):
            calls["messages"] = kwargs
            return [{"message_seq": 7, "role": "assistant", "content": "已生成预览"}], True

    monkeypatch.setattr("ai_erp_rag_assistant.app.api.session_repository", Repository())
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._persistent_identity",
        lambda request, authorization, uid: (request, {}, "16", "verified-863"),
    )

    sessions = session_list(
        SessionListRequest(user_id="untrusted", company_id="16", page=2, page_size=10),
        "Bearer token",
        "863",
    )
    messages = session_messages(
        SessionMessagesRequest(
            user_id="untrusted",
            company_id="16",
            session_id="session-1",
            before_seq=8,
            page_size=20,
        ),
        "Bearer token",
        "863",
    )

    assert sessions["items"][0]["session_id"] == "session-1"
    assert calls["sessions"]["user_id"] == "verified-863"
    assert calls["sessions"]["page"] == 2
    assert messages["next_before_seq"] == 7
    assert calls["messages"]["user_id"] == "verified-863"
    assert calls["messages"]["session_key"] == "session-1"


def test_session_read_api_reports_when_long_term_store_is_disabled(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.session_repository",
        SimpleNamespace(enabled=False),
    )

    with pytest.raises(HTTPException) as error:
        session_list(SessionListRequest(user_id="863", company_id="16"), None, None)

    assert error.value.status_code == 503

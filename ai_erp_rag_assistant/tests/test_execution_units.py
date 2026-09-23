from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from ai_erp_rag_assistant.app.api.routes.executions import execution_status
from ai_erp_rag_assistant.app.api.schemas import ChatRequest, ExecutionStatusRequest
from ai_erp_rag_assistant.app.services.execution_repository import (
    ExecutionRepository,
    ExecutionLeaseLostError,
    RunClaim,
    StepStart,
    _execution_state,
    execution_request_hash,
)
from ai_erp_rag_assistant.app.services.execution_runtime import (
    DurableExecutionContext,
    durable_node,
)
from ai_erp_rag_assistant.app.services.chat_execution_service import (
    finalize_chat_execution,
)


class _ClaimCursor:
    def __init__(self):
        self.lastrowid = 0
        self.rowcount = 1
        self.row = None
        self.run_key = ""
        self.queries = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, sql, params=None):
        compact = " ".join(sql.split())
        if params is not None:
            assert compact.count("%s") == len(params)
        self.queries.append((compact, params))
        if "SELECT id FROM ai_erp_assistants" in compact:
            self.row = {"id": 2}
        elif "INSERT INTO ai_erp_agent_runs" in compact:
            self.run_key = params[2]
            self.lastrowid = 10
            self.row = None
        elif "SELECT id, run_key" in compact:
            self.row = {
                "id": 10,
                "run_key": self.run_key,
                "session_key": "session-1",
                "user_id": "863",
                "request_id": "request-1",
                "request_hash": "h" * 64,
                "status": "running",
                "state_json": None,
                "result_json": None,
                "retry_count": 0,
                "owner_token": "",
                "lease_active": 1,
            }

    def fetchone(self):
        return self.row


class _ClaimConnection:
    def __init__(self):
        self.cursor_instance = _ClaimCursor()
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


class _FakeRepository:
    def __init__(self, *, cached: bool = False):
        self.cached = cached
        self.events: list[tuple[str, str]] = []

    def begin_step(self, **kwargs):
        self.events.append(("begin", kwargs["step_name"]))
        return StepStart(
            self.cached,
            {"erp_data": {"approval_id": "A-1"}} if self.cached else {},
        )

    def complete_step(self, **kwargs):
        self.events.append(("complete", kwargs["step_name"]))

    def fail_step(self, **kwargs):
        self.events.append(("failed", kwargs["step_name"]))


def test_execution_repository_creates_run_without_real_database(monkeypatch):
    connection = _ClaimConnection()
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.execution_repository.get_settings",
        lambda: SimpleNamespace(session_store="mysql"),
    )
    monkeypatch.setattr(
        ExecutionRepository,
        "_connect",
        staticmethod(lambda: connection),
    )

    claim = ExecutionRepository().claim_run(
        company_id="16",
        assistant_key="approval-assistant",
        session_key="session-1",
        user_id="863",
        request_id="request-1",
        request_hash="h" * 64,
    )

    assert connection.committed is True
    assert claim.context is not None
    assert len(claim.context.run_key) == 32
    assert claim.retry_count == 0
    sql = "\n".join(item[0] for item in connection.cursor_instance.queries)
    assert "INSERT INTO ai_erp_agent_runs" in sql
    assert "FOR UPDATE" in sql


def test_owned_run_rejects_expired_lease_without_touching_database():
    """租约失效时节点不能继续写入，查询必须带有效期条件。"""

    class Cursor:
        def __init__(self):
            self.sql = ""

        def execute(self, sql, params):
            self.sql = " ".join(sql.split())

        def fetchone(self):
            return None

    cursor = Cursor()
    with pytest.raises(ExecutionLeaseLostError):
        ExecutionRepository._owned_run(cursor, "r" * 32, "o" * 32)
    assert "lease_expires_at > CURRENT_TIMESTAMP(6)" in cursor.sql


def test_durable_step_reuses_completed_erp_output_without_calling_node():
    repository = _FakeRepository(cached=True)
    context = DurableExecutionContext(repository, "r" * 32, "o" * 32)

    result = context.execute_step(
        "approval.submit",
        {"preview": {"idempotency_key": "idem-1"}},
        lambda: (_ for _ in ()).throw(AssertionError("不应重复调用 ERP")),
        replay_completed=True,
    )

    assert result["erp_data"]["approval_id"] == "A-1"
    assert repository.events == [("begin", "approval.submit")]


def test_durable_step_records_failure_before_propagating_error():
    repository = _FakeRepository()
    context = DurableExecutionContext(repository, "r" * 32, "o" * 32)

    with pytest.raises(RuntimeError, match="ERP unavailable"):
        context.execute_step(
            "approval.submit",
            {"preview": {"idempotency_key": "idem-1"}},
            lambda: (_ for _ in ()).throw(RuntimeError("ERP unavailable")),
            replay_completed=True,
        )

    assert repository.events == [
        ("begin", "approval.submit"),
        ("failed", "approval.submit"),
    ]


def test_finalize_chat_execution_marks_durable_completion_failure():
    """Run 完成写入失败时，JSON 和 SSE 共用逻辑必须返回可重试失败状态。"""

    class Repository:
        failed_state = None

        @staticmethod
        def complete_run(**kwargs):
            raise RuntimeError("storage unavailable")

        def fail_run(self, **kwargs):
            self.failed_state = kwargs["state"]

    repository = Repository()
    context = DurableExecutionContext(
        repository,
        "r" * 32,
        "o" * 32,
        retry_count=2,
    )

    result = finalize_chat_execution(
        {
            "route": "approval_workflow",
            "assistant_type": "approval",
            "assistant_message": "已生成审批预览",
        },
        context,
        None,
    )

    assert isinstance(result.error, RuntimeError)
    assert result.state["execution_status"] == "failed"
    assert result.state["execution_retry_count"] == 2
    assert result.response.message == "执行失败，请稍后重试"
    assert result.response.run_id == "r" * 32
    assert repository.failed_state["execution_status"] == "failed"


def test_durable_node_is_noop_without_execution_context():
    wrapped = durable_node("planner", lambda state: {"route": state["route"]})

    result = wrapped(
        {"route": "general_chat"},
        {"configurable": {"thread_id": "thread-1"}},
    )

    assert result == {"route": "general_chat"}


def test_execution_checkpoint_removes_credentials_but_keeps_erp_result():
    snapshot = _execution_state(
        {
            "authorization": "Bearer secret",
            "preview": {
                "preview_id": "p-1",
                "token": "secret",
                "client_secret": "secret-client-value",
            },
            "erp_data": {"approval_id": "A-1", "accessToken": "secret-access-token"},
            "user_context": {"raw_userinfo": {"mobile": "secret"}},
        }
    )

    assert "authorization" not in snapshot
    assert snapshot["preview"] == {"preview_id": "p-1"}
    assert snapshot["erp_data"] == {"approval_id": "A-1"}
    assert "user_context" not in snapshot


def test_execution_request_hash_ignores_transport_fields_and_checks_business_input():
    base = ChatRequest(
        message="提交请假",
        session_id="session-1",
        request_id="request-1",
        assistant_key="approval-assistant",
        user_id="863",
        authorization="Bearer old",
    )
    same_business_request = base.model_copy(
        update={"authorization": "Bearer refreshed", "stream": True}
    )
    changed_business_request = base.model_copy(update={"message": "提交报销"})

    assert execution_request_hash(base, "approval-assistant") == execution_request_hash(
        same_business_request,
        "approval-assistant",
    )
    assert execution_request_hash(base, "approval-assistant") != execution_request_hash(
        changed_business_request,
        "approval-assistant",
    )


def test_execution_status_uses_verified_tenant_and_user(monkeypatch):
    captured = {}

    class Repository:
        enabled = True

        @staticmethod
        def get_status(**kwargs):
            captured.update(kwargs)
            now = datetime(2026, 9, 8, 10, 0, 0)
            return {
                "run_id": "r" * 32,
                "request_id": "request-1",
                "session_id": "session-1",
                "status": "failed",
                "current_step": "approval.submit",
                "state_version": 4,
                "retry_count": 1,
                "last_error_code": "step_failed",
                "last_error_message": "ERP unavailable",
                "recoverable": True,
                "lease_expires_at": None,
                "started_at": now,
                "completed_at": None,
                "created_at": now,
                "updated_at": now,
            }

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.routes.executions.persistent_identity",
        lambda request, authorization, uid: (request, {}, "16", "verified-863"),
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.routes.executions.execution_repository",
        Repository(),
    )

    response = execution_status(
        ExecutionStatusRequest(
            user_id="untrusted",
            assistant_key="approval-assistant",
            run_id="r" * 32,
        ),
        "Bearer local-test",
        "863",
    )

    assert response.status == "failed"
    assert response.recoverable is True
    assert response.last_error_message == "ERP 服务暂时不可用，请稍后重试"
    assert captured == {
        "company_id": "16",
        "assistant_key": "approval-assistant",
        "user_id": "verified-863",
        "run_key": "r" * 32,
    }


def test_approval_chat_returns_durable_run_metadata_without_real_database(monkeypatch):
    from fastapi.testclient import TestClient

    from ai_erp_rag_assistant.app.database import get_optional_db_session
    from ai_erp_rag_assistant.app.main import app
    from ai_erp_rag_assistant.app.api.routes import chat as chat_routes

    captured = {}

    class SessionRepository:
        enabled = True

        @staticmethod
        def assistant_available(**kwargs):
            return True

        @staticmethod
        def cached_response(**kwargs):
            return None

        @staticmethod
        def load_state(**kwargs):
            return {}

        @staticmethod
        def save_exchange(**kwargs):
            captured["exchange"] = kwargs

    class Context:
        run_key = "r" * 32
        retry_count = 2
        current_step = ""

        @staticmethod
        def complete(state, response):
            captured["completed_response"] = response

        @staticmethod
        def fail(state, error):
            raise AssertionError("成功路径不应标记失败")

    class ExecutionRepository:
        @staticmethod
        def claim_run(**kwargs):
            captured["claim"] = kwargs
            return RunClaim(Context(), None, {}, 2)

    class Workflow:
        @staticmethod
        def invoke(state, *, config):
            captured["config"] = config
            return {
                **state,
                "route": "approval_workflow",
                "assistant_message": "已生成审批预览",
                "workflow_status": "preview_ready",
            }

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.routes.chat.persistent_identity",
        lambda request, authorization, uid: (
            request,
            {"company_id": "16", "uid": "863", "erp_mode": "remote"},
            "16",
            "863",
        ),
    )
    monkeypatch.setattr(chat_routes, "session_repository", SessionRepository())
    monkeypatch.setattr(chat_routes, "execution_repository", ExecutionRepository())
    workflow = Workflow()
    monkeypatch.setattr(
        chat_routes,
        "_selected_workflows",
        lambda *args, **kwargs: (workflow, workflow),
    )
    app.dependency_overrides[get_optional_db_session] = lambda: None
    try:
        response = TestClient(app).post(
            "/api/chat",
            headers={"Authorization": "Bearer local-test", "UID": "863"},
            json={
                "message": "帮我发起请假审批",
                "session_id": "approval-1",
                "request_id": "request-1",
                "user_id": "863",
                "assistant_key": "approval-assistant",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    payload = response.json()
    assert payload["run_id"] == "r" * 32
    assert payload["execution_status"] == "completed"
    assert payload["execution_retry_count"] == 2
    assert captured["claim"]["company_id"] == "16"
    assert captured["config"]["configurable"]["durable_execution"].run_key == "r" * 32
    assert captured["completed_response"]["execution_status"] == "completed"

from types import SimpleNamespace

from fastapi.testclient import TestClient

from ai_erp_rag_assistant.app.api import _anonymize_trace
from ai_erp_rag_assistant.app.graph.state import initial_state
from ai_erp_rag_assistant.app.graph.workflow import (
    _extract_dynamic_duration_fields,
    _extract_dynamic_option_fields,
    _confirmation_mismatch,
    _route_from_start,
    _route_after_erp_context,
    _route_after_planner,
    _submission_fields,
    _validate_fields,
    accept_frozen_preview_confirmation,
    agent_planner,
    answer_with_llm,
    load_approval_template,
    load_erp_context,
    retrieve_rag,
    reject_out_of_scope,
    submit_if_confirmed,
    validate_and_preview,
)
from ai_erp_rag_assistant.app.services.model_service import ModelService
from ai_erp_rag_assistant.app.services.model_service import AgentPlan
from ai_erp_rag_assistant.app.services.milvus_service import MilvusService
from ai_erp_rag_assistant.app.rag_admin_repository import (
    RagKnowledgeBaseTarget,
    RagRuntimeConfig,
)
from scripts.ingest_pdf import document_metadata, infer_title, split_text


def test_langsmith_trace_anonymizer_redacts_credentials():
    sanitized = _anonymize_trace({
        "authorization": "opaque-erp-token",
        "nested": {"api_key": "private-key", "message": "keep me"},
    })

    assert sanitized["authorization"] == "[REDACTED]"
    assert sanitized["nested"]["api_key"] == "[REDACTED]"
    assert sanitized["nested"]["message"] == "keep me"


def test_initial_state_preserves_active_approval_context():
    prior = {
        "plan": {"approval_type": "报销"},
        "template": {"template_id": "12", "fields": [{"name": "amount"}]},
        "fields": {"amount": 100},
        "pending_question": "请补充发票日期",
        "active_approval": True,
    }

    state = initial_state("session", "user", "今天", prior=prior)

    assert state["plan"]["approval_type"] == "报销"
    assert state["template"]["template_id"] == "12"
    assert state["fields"] == {"amount": 100}
    assert state["pending_question"] == "请补充发票日期"
    assert state["active_approval"] is True


def test_prevalidated_erp_identity_is_reused_without_second_userinfo_call(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.get_current_user",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应重复调用用户信息接口")),
    )
    state = {
        "user_id": "863",
        "user_context": {
            "uid": "863",
            "company_id": "16",
            "department": "研发部",
            "erp_mode": "remote",
        },
        "tool_calls": [],
    }

    result = load_erp_context(state)

    assert result["user_context"]["company_id"] == "16"
    assert result["tool_calls"][-1]["reused"] is True


def test_initial_state_does_not_reactivate_closed_preview():
    state = initial_state(
        "session",
        "user",
        "你好",
        prior={
            "preview": {"idempotency_key": "closed-key"},
            "active_approval": False,
        },
    )

    assert state["preview"] == {}
    assert state["workflow_status"] == "idle"


def test_chat_endpoint_passes_selected_assistant_runtime_to_workflow(monkeypatch):
    from ai_erp_rag_assistant.app.database import get_optional_db_session
    from ai_erp_rag_assistant.app.main import app
    from ai_erp_rag_assistant.app.routes import chat as chat_routes

    runtime = RagRuntimeConfig(
        collection="",
        retrieval_scope="selected",
        knowledge_bases=(
            RagKnowledgeBaseTarget(
                knowledge_base_key="hr",
                knowledge_base_name="人事制度库",
                collection="company_16_hr",
                document_scope_loaded=True,
            ),
        ),
    )
    calls = {}

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._persistent_identity",
        lambda request, authorization, uid: (
            request,
            {"company_id": "16", "uid": "863", "erp_mode": "remote"},
            "16",
            "863",
        ),
    )

    def fake_runtime(db, **kwargs):
        calls["runtime_args"] = kwargs
        return runtime

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_runtime_config", fake_runtime
    )
    monkeypatch.setattr(
        type(chat_routes.session_repository),
        "enabled",
        property(lambda self: False),
    )

    class FakeWorkflow:
        @staticmethod
        def get_state(config):
            return None

        @staticmethod
        def invoke(state, *, config):
            calls["config"] = config
            return {
                **state,
                "route": "general_chat",
                "assistant_message": "你好",
            }

    monkeypatch.setattr(chat_routes, "workflow", FakeWorkflow())
    app.dependency_overrides[get_optional_db_session] = lambda: None
    try:
        response = TestClient(app).post(
            "/api/chat",
            headers={"Authorization": "Bearer local-test", "UID": "863"},
            json={
                "message": "你好",
                "session_id": "assistant-runtime-test",
                "user_id": "863",
                "assistant_key": "test-assistant",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert calls["runtime_args"] == {
        "company_id": "16",
        "knowledge_base_key": "",
        "assistant_key": "test-assistant",
    }
    assert calls["config"]["configurable"]["rag_runtime"] is runtime
    assert calls["config"]["metadata"]["assistant_key"] == "test-assistant"


def test_chat_endpoint_streams_only_answer_tokens_and_final_response(monkeypatch):
    from ai_erp_rag_assistant.app.database import get_optional_db_session
    from ai_erp_rag_assistant.app.main import app
    from ai_erp_rag_assistant.app.routes import chat as chat_routes

    runtime = RagRuntimeConfig(collection="company_16_hr")
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._persistent_identity",
        lambda request, authorization, uid: (
            request,
            {"company_id": "16", "uid": "863", "erp_mode": "remote"},
            "16",
            "863",
        ),
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_runtime_config",
        lambda db, **kwargs: runtime,
    )
    monkeypatch.setattr(
        type(chat_routes.session_repository),
        "enabled",
        property(lambda self: False),
    )

    class FakeWorkflow:
        @staticmethod
        def get_state(config):
            return None

        @staticmethod
        def stream(state, *, config, stream_mode):
            assert stream_mode == ["messages", "values"]
            # Planner 的结构化输出属于内部信息，不能作为回答 Token 发给前端。
            yield (
                "messages",
                (SimpleNamespace(content="内部计划"), {"langgraph_node": "agent_planner"}),
            )
            yield (
                "messages",
                (SimpleNamespace(content="你"), {"langgraph_node": "answer_with_llm"}),
            )
            yield (
                "messages",
                (SimpleNamespace(content="好"), {"langgraph_node": "answer_with_llm"}),
            )
            yield (
                "values",
                {
                    **state,
                    "route": "general_chat",
                    "assistant_message": "你好",
                },
            )

    monkeypatch.setattr(chat_routes, "workflow", FakeWorkflow())
    app.dependency_overrides[get_optional_db_session] = lambda: None
    try:
        with TestClient(app).stream(
            "POST",
            "/api/chat",
            headers={"Authorization": "Bearer local-test", "UID": "863"},
            json={
                "message": "你好",
                "session_id": "assistant-stream-test",
                "user_id": "863",
                "assistant_key": "test-assistant",
                "stream": True,
            },
        ) as response:
            body = "".join(response.iter_text())
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert 'event: token\ndata: {"content":"你"}' in body
    assert 'event: token\ndata: {"content":"好"}' in body
    assert "内部计划" not in body
    assert 'event: final\ndata: {"message":"你好"' in body
    assert body.rstrip().endswith("event: done\ndata: {}")


def test_retrieve_rag_uses_assistant_runtime_instead_of_default_collection(monkeypatch):
    runtime = RagRuntimeConfig(
        collection="",
        top_k=7,
        retrieval_scope="selected",
        knowledge_bases=(
            RagKnowledgeBaseTarget(
                knowledge_base_key="hr",
                knowledge_base_name="人事制度库",
                collection="company_16_hr",
                document_scope_loaded=True,
            ),
        ),
    )
    calls = {}

    def fake_search(query, **kwargs):
        calls.update({"query": query, **kwargs})
        return [
            {
                "chunk_id": "hr-1",
                "collection": "company_16_hr",
                "text": "病假制度",
            }
        ]

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.search_knowledge", fake_search
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.write_audit_event",
        lambda *args, **kwargs: None,
    )
    result = retrieve_rag(
        {
            "user_message": "一个月有多少病假",
            "plan": {"query": "病假天数"},
            "user_context": {
                "company_id": "16",
                "department": "研发部",
                "rag_access_tags": ["employee"],
            },
            "tool_calls": [],
        },
        {"configurable": {"rag_runtime": runtime}},
    )

    assert calls["runtime"] is runtime
    assert calls["top_k"] == 7
    assert calls["permission_tags"] == ["employee"]
    assert result["evidence"][0]["collection"] == "company_16_hr"
    assert result["tool_calls"][-1]["collections"] == ["company_16_hr"]


def test_knowledge_answer_uses_assistant_prompt_and_model_config(monkeypatch):
    runtime = RagRuntimeConfig(
        collection="company_16_hr",
        system_context="回答员工制度时使用正式中文。",
        model_overrides={"model": "configured-model", "temperature": 0.1},
    )
    calls = {}

    def fake_answer(question, **kwargs):
        calls.update({"question": question, **kwargs})
        return "每月病假规则以制度为准。"

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.model_service.answer", fake_answer
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.write_audit_event",
        lambda *args, **kwargs: None,
    )
    result = answer_with_llm(
        {
            "user_message": "一个月有多少病假",
            "route": "knowledge",
            "evidence": [{"chunk_id": "hr-1", "text": "病假制度"}],
            "tool_calls": [],
        },
        {"configurable": {"rag_runtime": runtime}},
    )

    assert result["assistant_message"] == "每月病假规则以制度为准。"
    assert calls["system_context"] == runtime.system_context
    assert calls["model_overrides"] == runtime.model_overrides


def test_agent_planner_uses_assistant_model_config(monkeypatch):
    runtime = RagRuntimeConfig(
        collection="company_16_hr",
        model_overrides={"model": "configured-model", "temperature": 0.1},
    )
    calls = {}

    def fake_plan(message, **kwargs):
        calls.update({"message": message, **kwargs})
        return SimpleNamespace(
            route="general_chat",
            decision="continue",
            fields={},
            approval_type="",
            model_dump=lambda: {
                "route": "general_chat",
                "decision": "continue",
                "fields": {},
                "approval_type": "",
            },
        )

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.model_service.plan", fake_plan
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.write_audit_event",
        lambda *args, **kwargs: None,
    )
    agent_planner(
        {"user_message": "你好", "tool_calls": []},
        {"configurable": {"rag_runtime": runtime}},
    )

    assert calls["model_overrides"] == runtime.model_overrides


def test_rag_assistant_blocks_approval_route_after_planning(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.model_service.plan",
        lambda *args, **kwargs: AgentPlan(
            route="approval_workflow",
            approval_type="请假",
        ),
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.write_audit_event",
        lambda *args, **kwargs: None,
    )

    planned = agent_planner(
        {
            "assistant_type": "rag",
            "user_message": "帮我发起请假",
            "tool_calls": [],
        },
        {"configurable": {"rag_runtime": RagRuntimeConfig(collection="")}},
    )

    assert planned["route"] == "general_chat"
    assert planned["plan"]["requested_route"] == "approval_workflow"
    assert _route_after_planner(planned) == "scope_blocked"
    rejected = reject_out_of_scope({**planned, "assistant_type": "rag"})
    assert rejected["workflow_status"] == "blocked"
    assert "审批助手" in rejected["assistant_message"]


def test_approval_assistant_keeps_draft_when_knowledge_route_is_blocked(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.model_service.plan",
        lambda *args, **kwargs: AgentPlan(route="knowledge", query="病假材料"),
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.write_audit_event",
        lambda *args, **kwargs: None,
    )

    planned = agent_planner(
        {
            "assistant_type": "approval",
            "user_message": "病假需要什么材料",
            "active_approval": True,
            "tool_calls": [],
        },
        {"configurable": {"rag_runtime": None}},
    )

    assert planned["plan"]["scope_blocked"] is True
    assert planned["active_approval"] is True


def test_approval_assistant_skips_rag_runtime_and_mysql_sessions(monkeypatch):
    from ai_erp_rag_assistant.app.database import get_optional_db_session
    from ai_erp_rag_assistant.app.main import app
    from ai_erp_rag_assistant.app.routes import chat as chat_routes

    calls = {}
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._persistent_identity",
        lambda request, authorization, uid: (
            request,
            {"company_id": "16", "uid": "863", "erp_mode": "remote"},
            "16",
            "863",
        ),
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_runtime_config",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("固定审批助手不应加载 RAG 配置")
        ),
    )
    monkeypatch.setattr(
        type(chat_routes.session_repository),
        "enabled",
        property(lambda self: True),
    )

    class FakeWorkflow:
        @staticmethod
        def get_state(config):
            calls["config"] = config
            return None

        @staticmethod
        def invoke(state, *, config):
            calls["state"] = state
            return {**state, "route": "general_chat", "assistant_message": "你好"}

    monkeypatch.setattr(chat_routes, "workflow", FakeWorkflow())
    app.dependency_overrides[get_optional_db_session] = lambda: None
    try:
        response = TestClient(app).post(
            "/api/chat",
            headers={"Authorization": "Bearer local-test", "UID": "863"},
            json={
                "message": "你好",
                "session_id": "fixed-approval-test",
                "user_id": "863",
                "assistant_key": "approval-assistant",
            },
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json()["assistant_type"] == "approval"
    assert calls["state"]["assistant_type"] == "approval"
    assert calls["config"]["configurable"]["rag_runtime"] is None


def test_explicit_confirmation_skips_planner_for_frozen_preview():
    state = {
        "user_message": "确认提交",
        "confirm": None,
        "active_approval": True,
        "preview": {
            "preview_id": "preview-1",
            "preview_version": 2,
            "requires_confirmation": True,
        },
        "tool_calls": [],
    }

    assert _route_from_start(state) == "frozen_confirmation"
    accepted = accept_frozen_preview_confirmation(state)
    assert accepted["confirm"] is True
    assert accepted["route"] == "approval_workflow"
    assert accepted["tool_calls"][-1]["tool"] == "workflow.preview_confirmed"


def test_confirmation_with_field_change_still_uses_planner():
    state = {
        "user_message": "确认前把原因修改为就医",
        "active_approval": True,
        "preview": {"requires_confirmation": True},
    }

    assert _route_from_start(state) == "planner"


def test_confirmation_routes_directly_to_frozen_preview_submission():
    route = _route_after_erp_context(
        {
            "route": "approval_workflow",
            "confirm": True,
            "preview": {"idempotency_key": "frozen-key"},
        }
    )

    assert route == "approval_submit"


def test_disabled_write_consumes_confirmation_without_reopening_draft(monkeypatch):
    preview = {
        "template_id": "5911",
        "fields": {"reason": "演示"},
        "idempotency_key": "frozen-key",
        "requires_confirmation": True,
    }
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.submit_approval",
        lambda frozen_preview, user: {
            "erp_write_mode": "disabled",
            "idempotency_key": frozen_preview["idempotency_key"],
        },
    )

    result = submit_if_confirmed(
        {
            "confirm": True,
            "preview": preview,
            "active_approval": True,
            "user_context": {},
            "tool_calls": [],
        }
    )

    assert result["preview"]["idempotency_key"] == "frozen-key"
    assert result["preview"]["requires_confirmation"] is False
    assert result["preview"]["confirmation_status"] == "write_disabled"
    assert result["active_approval"] is False
    assert result["confirm"] is None


def test_preview_has_stable_identity_and_new_version_after_change(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.get_approval_nodes",
        lambda *args, **kwargs: [],
    )
    base = {
        "template": {
            "template_id": "5911",
            "title": "请假申请",
            "fields": [{"name": "reason", "label": "原因", "required": True}],
        },
        "fields": {"reason": "就医"},
        "user_context": {},
        "plan": {"decision": "continue"},
        "tool_calls": [],
    }

    first = validate_and_preview(base)
    same = validate_and_preview({**base, "preview": first["preview"]})
    changed = validate_and_preview({
        **base,
        "fields": {"reason": "复诊"},
        "preview": first["preview"],
    })

    assert first["workflow_status"] == "preview_ready"
    assert first["preview"]["preview_version"] == 1
    assert same["preview"]["preview_id"] == first["preview"]["preview_id"]
    assert same["preview"]["preview_hash"] == first["preview"]["preview_hash"]
    assert same["preview"]["idempotency_key"] == first["preview"]["idempotency_key"]
    assert changed["preview"]["preview_version"] == 2
    assert changed["preview"]["preview_id"] != first["preview"]["preview_id"]
    assert changed["preview"]["idempotency_key"] != first["preview"]["idempotency_key"]


def test_stale_preview_confirmation_is_rejected_before_erp_submit(monkeypatch):
    submit_calls: list[dict] = []
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.submit_approval",
        lambda preview, user: submit_calls.append(preview),
    )
    state = {
        "confirm": True,
        "confirm_preview_id": "old-preview",
        "preview": {
            "preview_id": "latest-preview",
            "preview_version": 2,
            "preview_hash": "latest-hash",
        },
        "tool_calls": [],
    }

    assert _confirmation_mismatch(state).startswith("预览标识已变化")
    result = submit_if_confirmed(state)

    assert submit_calls == []
    assert result["workflow_status"] == "preview_ready"
    assert result["confirm"] is None


def test_validate_fields_checks_options_and_time_order():
    template = {
        "fields": [
            {"name": "leave_type", "label": "请假类型", "required": True, "options": ["事假", "病假"]},
            {"name": "start_time", "label": "开始时间", "required": True},
            {"name": "end_time", "label": "结束时间", "required": True},
        ]
    }

    missing, invalid = _validate_fields(
        template,
        {
            "leave_type": "年假",
            "start_time": "2026-08-17T17:00:00",
            "end_time": "2026-08-17T09:00:00",
        },
    )

    assert missing == []
    assert "请假类型必须是：事假、病假" in invalid
    assert "结束时间必须晚于开始时间" in invalid


def test_template_change_does_not_keep_old_fields(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.list_approval_templates",
        lambda query, company_id, user: [{"template_id": "expense", "title": "报销申请"}],
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.get_approval_template",
        lambda template_id, company_id, title, user: {
            "template_id": "expense",
            "title": "报销申请",
            "fields": [{"name": "amount", "label": "金额", "required": True}],
            "erp_mode": "mock",
        },
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.model_service.extract_approval_fields",
        lambda *args, **kwargs: {"amount": 88},
    )
    state = {
        "user_message": "改成报销 88 元",
        "user_context": {"company_id": "lanjing"},
        "plan": {"approval_type": "报销", "fields": {}, "decision": "continue"},
        "template": {
            "template_id": "leave",
            "requested_approval_type": "请假",
            "fields": [{"name": "reason"}],
        },
        "fields": {"reason": "旧请假原因"},
        "tool_calls": [],
    }

    result = load_approval_template(state)

    assert result["fields"] == {"amount": 88}


def test_unique_relevant_template_is_selected_without_llm_call(monkeypatch):
    service = ModelService()
    monkeypatch.setattr(
        service,
        "_invoke",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应调用 LLM")),
    )

    selected = service.select_template(
        "帮我明天下午请半天病假",
        [{"template_id": "5911", "title": "请假申请"}],
    )

    assert selected == "5911"


def test_dynamic_leave_option_binds_to_real_erp_field_key():
    template_fields = [
        {
            "name": "rest_holiday_rule_id",
            "label": "请假类型",
            "type": "enum",
            "options": ["病假（余10天）", "事假", "调休假（余8小时）"],
            "option_values": [
                {"label": "病假（余10天）", "value": 12},
                {"label": "事假", "value": 13},
                {"label": "调休假（余8小时）", "value": 11},
            ],
        }
    ]

    matched = _extract_dynamic_option_fields(
        "帮我明天下午请半天病假",
        template_fields,
    )

    assert matched == {"rest_holiday_rule_id": "病假（余10天）"}
    assert _submission_fields(
        {"fields": template_fields},
        matched,
    ) == {"rest_holiday_rule_id": 12}


def test_natural_half_day_binds_to_real_erp_duration_field():
    fields = [
        {
            "name": "rest_duration",
            "label": "请假时长",
            "type": "number",
            "erp_field_type": "duration",
            "required": True,
        }
    ]

    assert _extract_dynamic_duration_fields("帮我明天下午请半天病假", fields) == {
        "rest_duration": 0.5,
    }
    assert _extract_dynamic_duration_fields("我要请2.5天事假", fields) == {
        "rest_duration": 2.5,
    }


def test_dynamic_option_match_does_not_guess_ambiguous_core_label():
    fields = [
        {
            "name": "rest_holiday_rule_id",
            "options": ["年假（2025余额）", "年假（2026余额）"],
        }
    ]

    assert _extract_dynamic_option_fields("我要请年假", fields) == {}


def test_load_template_maps_leave_type_and_duration_and_drops_generic_planner_fields(monkeypatch):
    template_fields = [
        {
            "name": "rest_holiday_rule_id",
            "label": "请假类型",
            "type": "enum",
            "required": True,
            "options": ["病假", "事假"],
            "option_values": [
                {"label": "病假", "value": 12},
                {"label": "事假", "value": 13},
            ],
        },
        {
            "name": "rest_duration",
            "label": "请假时长",
            "type": "number",
            "erp_field_type": "duration",
            "required": True,
        },
    ]
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.list_approval_templates",
        lambda query, company_id, user: [{"template_id": "5911", "title": "请假申请"}],
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.get_approval_template",
        lambda template_id, company_id, title, user: {
            "template_id": template_id,
            "title": title,
            "fields": template_fields,
            "erp_mode": "remote",
        },
    )

    def fake_extract(*args, **kwargs):
        assert kwargs["known_fields"] == {
            "rest_holiday_rule_id": "病假",
            "rest_duration": 0.5,
        }
        return {}

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.graph.workflow.model_service.extract_approval_fields",
        fake_extract,
    )
    state = {
        "user_message": "帮我明天下午请半天病假",
        "user_context": {"company_id": "C001"},
        "plan": {
            "approval_type": "病假",
            "fields": {"leave_type": "病假"},
            "decision": "continue",
        },
        "fields": {"leave_type": "病假"},
        "template": {},
        "template_candidates": [],
        "tool_calls": [],
    }

    result = load_approval_template(state)

    assert result["fields"] == {
        "rest_holiday_rule_id": "病假",
        "rest_duration": 0.5,
    }
    assert result["tool_calls"][-1]["matched_option_fields"] == ["rest_holiday_rule_id"]
    assert result["tool_calls"][-1]["matched_duration_fields"] == ["rest_duration"]


def test_pdf_helpers_keep_semantic_metadata():
    class Settings:
        rag_company_id = "lanjing"
        rag_department = "公共制度"
        rag_permission_tags = ["knowledge:employee_handbook"]

    chunks = split_text("第一句说明。第二句说明。第三句说明。", size=12, overlap=2)
    metadata = document_metadata(
        type("PdfPath", (), {"stem": "员工手册（2026修订版）"})(),
        "生效日期：2026 年 4 月 11 日",
        Settings(),
    )

    assert len(chunks) >= 2
    assert chunks[0].endswith("。")
    assert infer_title("第六章 考勤管理制度 具体内容", "员工手册") == "第六章 考勤管理制度 具体内容"
    assert metadata["version"] == "2026"
    assert metadata["effective_date"] == "2026-04-11"


def test_knowledge_answer_appends_deduplicated_citations():
    answer = ModelService._append_citations(
        "病假需要提供相关材料。",
        [
            {"source": "员工手册.pdf", "page": 9},
            {"source": "员工手册.pdf", "page": 9},
            {"source": "员工手册.pdf", "page": 10},
        ],
    )

    assert answer.count("第 9 页") == 1
    assert "第 10 页" in answer


def test_rerank_accepts_only_input_chunks_and_keeps_stable_fallback(monkeypatch):
    service = ModelService()
    monkeypatch.setattr(service, "is_configured", lambda: True)
    monkeypatch.setattr(
        service,
        "_invoke",
        lambda *args, **kwargs: {
            "items": [
                {"chunk_id": "chunk-2", "relevance": 0.95},
                {"chunk_id": "invented", "relevance": 1.0},
            ]
        },
    )

    evidence = service.rerank(
        "病假材料",
        [
            {"chunk_id": "chunk-1", "text": "年假", "score": 0.9},
            {"chunk_id": "chunk-2", "text": "病假证明", "score": 0.8},
        ],
        top_k=2,
    )

    assert [item["chunk_id"] for item in evidence] == ["chunk-2", "chunk-1"]
    assert evidence[0]["rerank_score"] == 0.95
    assert all(item["chunk_id"] != "invented" for item in evidence)


def test_structured_citations_keep_source_page_score_and_snippet():
    citations = ModelService.build_citations(
        [
            {
                "chunk_id": "chunk-9",
                "source": "员工手册.pdf",
                "title": "病假制度",
                "page": 9,
                "text": "病假需要提供医院证明。",
                "rerank_score": 0.96,
            }
        ]
    )

    assert citations == [
        {
            "citation_id": 1,
            "chunk_id": "chunk-9",
            "source": "员工手册.pdf",
            "title": "病假制度",
            "page": 9,
            "score": 0.96,
            "snippet": "病假需要提供医院证明。",
        }
    ]


def test_structured_citations_keep_same_file_page_from_different_knowledge_bases():
    citations = ModelService.build_citations(
        [
            {
                "chunk_id": "hr-1",
                "knowledge_base_key": "hr",
                "knowledge_base_name": "员工制度",
                "source": "制度.pdf",
                "page": 1,
                "text": "员工制度",
            },
            {
                "chunk_id": "finance-1",
                "knowledge_base_key": "finance",
                "knowledge_base_name": "财务制度",
                "source": "制度.pdf",
                "page": 1,
                "text": "财务制度",
            },
        ]
    )

    assert [item["knowledge_base_key"] for item in citations] == ["hr", "finance"]
    assert [item["knowledge_base_name"] for item in citations] == ["员工制度", "财务制度"]


def test_model_overrides_allow_generation_controls_only():
    safe = ModelService._safe_model_overrides(
        {
            "model": "qwen-plus",
            "temperature": 0.7,
            "max_tokens": 2048,
            "api_key": "must-not-pass",
            "base_url": "https://attacker.invalid",
            "unknown": True,
        }
    )

    assert safe == {"model": "qwen-plus", "temperature": 0.7, "max_tokens": 2048}


def test_model_overrides_reject_invalid_generation_values():
    assert ModelService._safe_model_overrides(
        {"temperature": 3, "max_tokens": 0, "model": ""}
    ) == {}


def test_answer_passes_model_overrides_to_the_llm_boundary(monkeypatch):
    calls = {}

    class FakeModel:
        def invoke(self, _messages):
            return SimpleNamespace(content="回答")

    service = ModelService()

    def fake_model(overrides=None):
        calls["overrides"] = overrides
        return FakeModel()

    monkeypatch.setattr(service, "_model", fake_model)

    assert service.answer(
        "问题",
        route="general_chat",
        model_overrides={"model": "qwen-plus", "temperature": 0.4},
    ) == "回答"
    assert calls["overrides"] == {"model": "qwen-plus", "temperature": 0.4}


def test_planner_decision_normalization_accepts_only_explicit_actions():
    assert ModelService._normalize_decision("continue") == "continue"
    assert ModelService._normalize_decision("confirm") == "confirm"
    assert ModelService._normalize_decision("cancel") == "cancel"
    assert ModelService._normalize_decision("or") == "continue"
    assert ModelService._normalize_decision("continue or confirm or cancel") == "continue"


def test_planner_decision_normalization_uses_explicit_user_confirmation():
    assert ModelService._normalize_decision("or", message="确认提交") == "confirm"
    assert ModelService._normalize_decision("invalid", message="请取消提交") == "cancel"
    assert ModelService._normalize_decision("confirm", message="我只是补充字段") == "confirm"


def test_milvus_search_does_not_require_local_knowledge_permission(monkeypatch):
    class FakeClient:
        def has_collection(self, name):
            return True

        def search(self, **kwargs):
            self.filter = kwargs["filter"]
            return [[{"entity": {"chunk_id": "c1", "text": "制度内容"}, "distance": 0.9}]]

    client = FakeClient()
    service = MilvusService()
    monkeypatch.setattr(service, "_client", lambda: client)
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.milvus_service.embedding_service.embed_query",
        lambda query: [0.1, 0.2],
    )

    evidence = service.search(
        "病假材料",
        company_id="lanjing",
        department="研发部",
        permission_tags=[],
    )

    assert evidence[0]["chunk_id"] == "c1"
    assert "company_id == \"lanjing\"" in client.filter
    assert "array_contains_any" not in client.filter

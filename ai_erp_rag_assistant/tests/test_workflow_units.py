from types import SimpleNamespace

from ai_erp_rag_assistant.app.api import _anonymize_trace
from ai_erp_rag_assistant.app.graph.state import initial_state
from ai_erp_rag_assistant.app.graph.workflow import (
    _extract_dynamic_duration_fields,
    _extract_dynamic_option_fields,
    _confirmation_mismatch,
    _route_from_start,
    _route_after_erp_context,
    _submission_fields,
    _validate_fields,
    accept_frozen_preview_confirmation,
    load_approval_template,
    load_erp_context,
    submit_if_confirmed,
    validate_and_preview,
)
from ai_erp_rag_assistant.app.services.model_service import ModelService
from ai_erp_rag_assistant.app.services.milvus_service import MilvusService
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

from __future__ import annotations

import importlib

from app.graph.state import initial_state


def test_agentic_daily_report_trigger_routes_to_demo_node() -> None:
    approval_agent = importlib.import_module("app.agents.approval_agent")
    state = initial_state("S-agentic-demo-route", "863")
    state["user_message"] = "演示 agentic workflow 日报：今天完成接口联调"

    result = approval_agent.intent_router_node(state)

    assert result["intent"] == "daily_report"
    assert result["daily_report_mode"] == "agentic_workflow_demo"
    assert result["_route"] == "daily_report_agentic_workflow_demo"


def test_agentic_daily_report_demo_workflow_exposes_agent_decision_and_gate_nodes() -> None:
    workflow_module = importlib.import_module(
        "app.graph.daily_report_agentic_workflow_demo"
    )

    graph = workflow_module.create_daily_report_agentic_workflow_demo().get_graph()

    assert "demo_agent_plan" in graph.nodes
    assert "demo_confirm_date" in graph.nodes
    assert "demo_load_context" in graph.nodes
    assert "demo_agent_compose" in graph.nodes
    assert "demo_save_draft" in graph.nodes
    assert "demo_preview_gate" in graph.nodes
    assert "demo_submit_gate" in graph.nodes


def test_agentic_daily_report_demo_node_uses_agent_plan_before_workflow_gates(
    monkeypatch,
) -> None:
    demo_module = importlib.import_module(
        "app.agents.daily_report_agentic_workflow_demo"
    )
    monkeypatch.setattr(
        demo_module,
        "_current_daily_report_date",
        lambda: "2026-07-02",
    )
    state = initial_state("S-agentic-demo-node", "863")
    state.update(
        {
            "user_message": "演示 agentic workflow 日报：今天完成接口联调，修复日报保存 bug",
            "uid": "863",
            "authorization": "Bearer token",
        }
    )

    result = demo_module.daily_report_agentic_workflow_demo_node(state)

    assert result["daily_report_mode"] == "agentic_workflow_demo"
    assert result["daily_report_date"] == "2026-07-02"
    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["daily_report_payload"]["date"] == "2026-07-02"
    assert "接口联调" in result["daily_report_payload"]["content"]
    assert isinstance(result["daily_report_payload"]["extends"], dict)
    assert isinstance(result["daily_report_payload"]["extend_fields"], list)
    assert {
        "type",
        "date",
        "content",
        "files",
        "at_uids",
        "recipients",
        "cc_recipients",
        "extends",
        "extend_fields",
    }.issubset(result["daily_report_payload"].keys())
    assert result["daily_report_agentic_plan"]["next_action"] == "ready_to_save"
    assert result["daily_report_agentic_compose"]["next_action"] == "save_draft"
    assert result["daily_report_agentic_demo_events"] == [
        "agent:plan",
        "workflow:confirm_date",
        "workflow:load_context",
        "agent:compose",
        "workflow:save_draft",
        "workflow:preview_gate",
    ]
    assert "agentic workflow 演示" in result["assistant_message"]
    assert "回复“确认提交”才会进入提交 gate" in result["assistant_message"]


def test_agentic_daily_report_demo_node_loads_context_via_tool(monkeypatch) -> None:
    demo_module = importlib.import_module(
        "app.agents.daily_report_agentic_workflow_demo"
    )
    monkeypatch.setattr(
        demo_module,
        "_current_daily_report_date",
        lambda: "2026-07-02",
    )
    calls: list[dict] = []

    class FakeContext:
        def __init__(self) -> None:
            self.default_payload = {
                "type": 1,
                "date": "2026-07-02",
                "content": "接口联调",
                "files": [],
                "at_uids": [],
                "recipients": [{"relate_id": 959, "relate_name": "演示汇报人"}],
                "cc_recipients": [],
                "extends": {"field_demo_mood": {"value": "稳步推进"}},
                "extend_fields": [
                    {
                        "field_key": "field_demo_mood",
                        "field_name": "今日状态",
                        "field_type": "input",
                        "is_system": 0,
                        "is_required": 0,
                    }
                ],
            }

        def model_dump(self):
            return {
                "report_type": 1,
                "report_date": "2026-07-02",
                "form_fields_payload": {"data": []},
                "config": {"parse_recipients": []},
                "draft": {},
                "sync_data": [{"title": "接口联调"}],
                "default_payload": self.default_payload,
            }

    monkeypatch.setattr(
        demo_module.daily_report_tools,
        "load_daily_report_context",
        type(
            "FakeTool",
            (),
            {
                "invoke": staticmethod(
                    lambda payload: calls.append(payload) or FakeContext().model_dump()
                )
            },
        )(),
    )

    state = initial_state("S-agentic-demo-load-context", "863")
    state.update(
        {
            "user_message": "演示 agentic workflow 日报：今天完成接口联调",
            "uid": "863",
            "authorization": "Bearer token",
        }
    )

    result = demo_module.daily_report_agentic_workflow_demo_node(state)

    assert calls == [
        {
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer token",
            "report_type": 1,
            "report_date": "2026-07-02",
        }
    ]
    assert "接口联调" in result["daily_report_payload"]["content"]
    assert result["daily_report_agentic_context"]["source"] == "agentic_workflow_demo"
    assert result["daily_report_agentic_context"]["sync_data"] == [{"title": "接口联调"}]


def test_agentic_daily_report_demo_node_asks_for_content_when_user_has_not_written_it(
    monkeypatch,
) -> None:
    demo_module = importlib.import_module(
        "app.agents.daily_report_agentic_workflow_demo"
    )
    monkeypatch.setattr(
        demo_module,
        "_current_daily_report_date",
        lambda: "2026-07-02",
    )

    class FakeContext:
        def model_dump(self):
            return {
                "report_type": 1,
                "report_date": "2026-07-02",
                "form_fields_payload": {"data": []},
                "config": {"parse_recipients": []},
                "draft": {},
                "sync_data": [{"title": "接口联调"}],
                "default_payload": {
                    "type": 1,
                    "date": "2026-07-02",
                    "content": "接口联调",
                    "files": [],
                    "at_uids": [],
                    "recipients": [],
                    "cc_recipients": [],
                    "extends": {},
                    "extend_fields": [],
                },
            }

    monkeypatch.setattr(
        demo_module.daily_report_tools,
        "load_daily_report_context",
        type(
            "FakeTool",
            (),
            {"invoke": staticmethod(lambda payload: FakeContext().model_dump())},
        )(),
    )

    state = initial_state("S-agentic-demo-missing-content", "863")
    state.update(
        {
            "user_message": "演示 agentic workflow 日报",
            "uid": "863",
            "authorization": "Bearer token",
        }
    )

    result = demo_module.daily_report_agentic_workflow_demo_node(state)

    assert result["status"] == "collecting"
    assert result["daily_report_agentic_compose"]["next_action"] == "ask_content"
    assert result["daily_report_payload"]["content"] == ""
    assert "请补充" in result["assistant_message"]
    assert "接口联调" not in result["assistant_message"]

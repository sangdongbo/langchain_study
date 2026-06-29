from __future__ import annotations

import importlib
import json
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

def test_daily_report_create_agent_factory_builds_autonomous_agent(monkeypatch) -> None:
    module = importlib.import_module("app.agents.daily_report_create_agent")
    calls: list[dict] = []

    def fake_backend(*, model, tools, prompt):
        calls.append({"model": model, "tools": tools, "prompt": prompt})
        return {"kind": "autonomous_daily_report_agent"}

    monkeypatch.setattr(module, "_create_agent_backend", lambda: fake_backend)

    agent = module.create_daily_report_create_agent(model="fake-model")

    assert agent == {"kind": "autonomous_daily_report_agent"}
    assert calls == [
            {
                "model": "fake-model",
                "tools": module.DAILY_REPORT_CREATE_AGENT_TOOLS,
                "prompt": module.DAILY_REPORT_CREATE_AGENT_PROMPT,
            }
        ]


def test_daily_report_create_agent_prompt_keeps_erp_guardrails() -> None:
    module = importlib.import_module("app.agents.daily_report_create_agent")

    prompt = module.DAILY_REPORT_CREATE_AGENT_PROMPT

    assert "先确认日志日期" in prompt
    assert "get_current_daily_report_date" in prompt
    assert "/oa/dailyReport/add" in prompt
    assert "用户明确确认提交" in prompt
    assert "不要丢弃 extends" in prompt


def test_current_daily_report_date_tool_returns_backend_today(monkeypatch) -> None:
    module = importlib.import_module("app.agents.daily_report_create_agent")

    class FakeDate:
        @classmethod
        def today(cls):
            return type("FakeToday", (), {"isoformat": lambda self: "2026-06-29"})()

    monkeypatch.setattr(module, "date", FakeDate)

    result = module.get_current_daily_report_date.invoke({})

    assert result == {"date": "2026-06-29"}


def test_daily_report_create_agent_tools_include_current_date_tool() -> None:
    module = importlib.import_module("app.agents.daily_report_create_agent")

    tool_names = [tool.name for tool in module.DAILY_REPORT_CREATE_AGENT_TOOLS]

    assert "get_current_daily_report_date" in tool_names
    assert tool_names.index("get_current_daily_report_date") < tool_names.index(
        "load_daily_report_context"
    )


def test_daily_report_create_agent_is_not_existing_daily_report_workflow() -> None:
    workflow_module = importlib.import_module("app.graph.daily_report_workflow")

    graph = workflow_module.create_daily_report_workflow().get_graph()

    assert "daily_report_create_agent" not in graph.nodes
    assert "daily_report_action" in graph.nodes


def test_daily_report_create_agent_node_adapts_approval_state_to_agent_messages(monkeypatch) -> None:
    module = importlib.import_module("app.agents.daily_report_create_agent")
    state_module = importlib.import_module("app.graph.state")
    calls: list[dict] = []

    class FakeAgent:
        def invoke(self, payload):
            calls.append(payload)
            return {
                "messages": [
                    AIMessage(content="已生成自主版日报预览，请确认是否提交。")
                ]
            }

    monkeypatch.setattr(module, "create_daily_report_create_agent", lambda model: FakeAgent())
    monkeypatch.setattr(module, "_build_daily_report_create_model", lambda: "fake-model")

    state = state_module.initial_state("S-create-node", "863")
    state.update(
        {
            "uid": "863",
            "authorization": "Bearer token",
            "user_message": "用自主版写今天日报",
            "trace": ["memory_agent", "intent_router"],
        }
    )

    result = module.daily_report_create_agent_node(state)

    assert calls == [
        {
            "messages": [
                {
                    "role": "user",
                    "content": (
                        "用户ID：863\n"
                        "ERP UID：863\n"
                        "ERP Authorization：Bearer token\n\n"
                        "用自主版写今天日报"
                    ),
                }
            ]
        }
    ]
    assert result["intent"] == "daily_report"
    assert result["daily_report_mode"] == "autonomous"
    assert result["assistant_message"] == "已生成自主版日报预览，请确认是否提交。"
    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["trace"] == [
        "memory_agent",
        "intent_router",
        "daily_report_create_agent",
    ]
    assert result["_route"] == "end"


def test_daily_report_create_agent_node_preserves_agent_message_history(monkeypatch) -> None:
    module = importlib.import_module("app.agents.daily_report_create_agent")
    state_module = importlib.import_module("app.graph.state")
    calls: list[dict] = []
    preview_message = AIMessage(content="已生成预览：今日完成客户跟进。请确认是否提交。")
    tool_message = ToolMessage(
        content='{"payload":{"date":"2026-06-24","content":"今日完成客户跟进"}}',
        tool_call_id="tool-1",
    )

    class FakeAgent:
        def invoke(self, payload):
            calls.append(payload)
            return {"messages": [*payload["messages"], preview_message, tool_message]}

    monkeypatch.setattr(module, "create_daily_report_create_agent", lambda model: FakeAgent())
    monkeypatch.setattr(module, "_build_daily_report_create_model", lambda: "fake-model")

    state = state_module.initial_state("S-create-history", "863")
    state.update(
        {
            "daily_report_agent_messages": [{"role": "user", "content": "上一轮用户消息"}],
            "user_message": "确认提交",
        }
    )

    result = module.daily_report_create_agent_node(state)

    assert calls[0]["messages"][0] == HumanMessage(content="上一轮用户消息")
    assert calls[0]["messages"][-1] == {
        "role": "user",
        "content": "用户ID：863\nERP UID：\nERP Authorization：\n\n确认提交",
    }
    assert result["assistant_message"] == "已生成预览：今日完成客户跟进。请确认是否提交。"
    assert result["status"] == "awaiting_daily_report_confirmation"
    assert result["daily_report_agent_messages"] == [
        {"role": "user", "content": "上一轮用户消息"},
        calls[0]["messages"][-1],
        {"role": "assistant", "content": "已生成预览：今日完成客户跟进。请确认是否提交。"},
        {
            "role": "tool",
            "content": '{"payload":{"date":"2026-06-24","content":"今日完成客户跟进"}}',
            "tool_call_id": "tool-1",
        },
    ]


def test_daily_report_create_agent_node_returns_json_serializable_messages(monkeypatch) -> None:
    module = importlib.import_module("app.agents.daily_report_create_agent")
    state_module = importlib.import_module("app.graph.state")

    class FakeAgent:
        def invoke(self, payload):
            return {
                "messages": [
                    *payload["messages"],
                    AIMessage(content="已生成预览，请确认是否提交。"),
                    ToolMessage(content='{"ok":true}', tool_call_id="tool-1"),
                ]
            }

    monkeypatch.setattr(module, "create_daily_report_create_agent", lambda model: FakeAgent())
    monkeypatch.setattr(module, "_build_daily_report_create_model", lambda: "fake-model")

    state = state_module.initial_state("S-create-json", "863")
    state.update(
        {
            "daily_report_agent_messages": [{"role": "user", "content": "上一轮用户消息"}],
            "user_message": "确认提交",
        }
    )

    result = module.daily_report_create_agent_node(state)

    json.dumps(result, ensure_ascii=False)
    assert result["daily_report_agent_messages"][0] == {"role": "user", "content": "上一轮用户消息"}
    assert result["daily_report_agent_messages"][-2] == {
        "role": "assistant",
        "content": "已生成预览，请确认是否提交。",
    }
    assert result["daily_report_agent_messages"][-1] == {
        "role": "tool",
        "content": '{"ok":true}',
        "tool_call_id": "tool-1",
    }


def test_daily_report_create_agent_preserves_tool_calls_in_message_history() -> None:
    module = importlib.import_module("app.agents.daily_report_create_agent")
    ai_message = AIMessage(
        content="",
        tool_calls=[
            {
                "name": "load_daily_report_context",
                "args": {"report_date": "2026-06-29"},
                "id": "tool-1",
                "type": "tool_call",
            }
        ],
    )

    saved = module._serializable_messages(
        [
            ai_message,
            ToolMessage(content='{"ok":true}', tool_call_id="tool-1"),
        ]
    )
    restored = [module._message_for_agent(message) for message in saved]

    json.dumps(saved, ensure_ascii=False)
    assert saved[0]["tool_calls"] == [
        {
            "name": "load_daily_report_context",
            "args": {"report_date": "2026-06-29"},
            "id": "tool-1",
            "type": "tool_call",
        }
    ]
    assert isinstance(restored[0], AIMessage)
    assert restored[0].tool_calls == saved[0]["tool_calls"]
    assert isinstance(restored[1], ToolMessage)
    assert restored[1].tool_call_id == "tool-1"


def test_guarded_submit_tool_requires_user_confirmation(monkeypatch) -> None:
    module = importlib.import_module("app.agents.daily_report_create_agent")
    calls: list[dict] = []

    class FakeService:
        def submit_payload(self, user, payload):
            calls.append(payload)
            return type(
                "SubmitResult",
                (),
                {
                    "model_dump": lambda self: {
                        "report_id": "1001",
                        "status": "success",
                        "raw_data": {},
                    }
                },
            )()

    monkeypatch.setattr(module.daily_report_tools, "daily_report_service", FakeService())

    rejected = module.guarded_submit_daily_report.invoke(
        {
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer token",
            "payload": {"content": "今日完成客户跟进"},
            "confirmed": False,
        }
    )
    accepted = module.guarded_submit_daily_report.invoke(
        {
            "user_id": "863",
            "uid": "863",
            "authorization": "Bearer token",
            "payload": {"content": "今日完成客户跟进"},
            "confirmed": True,
        }
    )

    assert rejected == {
        "code": 400,
        "message": "提交日报前必须先展示预览，并由用户明确确认提交。",
    }
    assert accepted["status"] == "success"
    assert calls == [{"content": "今日完成客户跟进"}]

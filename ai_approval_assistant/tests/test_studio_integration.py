from __future__ import annotations

import importlib
import json
from pathlib import Path


def test_langgraph_json_points_to_importable_compiled_graph() -> None:
    config_path = Path(__file__).resolve().parents[1] / "langgraph.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))

    graph_ref = config["graphs"]["approval_assistant"]
    module_name, variable_name = graph_ref.split(":")
    module = importlib.import_module(module_name)
    graph = getattr(module, variable_name)

    assert graph.get_graph().nodes
    assert "memory_agent" in graph.get_graph().nodes
    assert "user_profile_agent" in graph.get_graph().nodes
    assert "intent_router" in graph.get_graph().nodes
    assert "user_info_agent" in graph.get_graph().nodes
    assert "approval_creation_agent" in graph.get_graph().nodes
    assert "daily_report_chat_agent" in graph.get_graph().nodes
    assert "daily_report_form_agent" not in graph.get_graph().nodes
    edges = {(edge.source, edge.target) for edge in graph.get_graph().edges}
    assert ("memory_agent", "intent_router") in edges
    assert ("user_profile_agent", "user_info_agent") in edges
    assert ("daily_report_chat_agent", "__end__") in edges
    assert ("memory_agent", "user_profile_agent") not in edges
    assert "load_context" not in graph.get_graph().nodes
    assert "collect" not in graph.get_graph().nodes


def test_workflow_factories_live_in_graph_layer_not_agent_layer() -> None:
    graph_module = importlib.import_module("app.graph.approval_workflow")
    agent_module = importlib.import_module("app.agents.approval_agent")

    assert hasattr(graph_module, "create_workflow")
    assert hasattr(graph_module, "create_approval_creation_workflow")
    assert not hasattr(agent_module, "create_workflow")
    assert not hasattr(agent_module, "create_approval_creation_workflow")


def test_intent_router_routes_daily_report_requests_to_chat_agent() -> None:
    module = importlib.import_module("app.agents.approval_agent")
    state = module.initial_state("S-daily-router", "863")
    state["user_message"] = "写今天日报"

    result = module.intent_router_node(state)

    assert result["intent"] == "daily_report"
    assert result["_route"] == "daily_report_chat_agent"


def test_intent_router_keeps_daily_report_confirmation_on_chat_agent() -> None:
    module = importlib.import_module("app.agents.approval_agent")
    state = module.initial_state("S-daily-confirm-router", "863")
    state.update(
        {
            "status": "awaiting_daily_report_confirmation",
            "user_message": "确认提交",
        }
    )

    result = module.intent_router_node(state)

    assert result["intent"] == "daily_report"
    assert result["_route"] == "daily_report_chat_agent"


def test_intent_router_keeps_daily_report_content_followup_on_chat_agent() -> None:
    module = importlib.import_module("app.agents.approval_agent")
    state = module.initial_state("S-daily-content-router", "863")
    state.update(
        {
            "status": "collecting",
            "awaiting_field": "daily_report_content",
            "user_message": "今天完成客户跟进",
        }
    )

    result = module.intent_router_node(state)

    assert result["intent"] == "daily_report"
    assert result["_route"] == "daily_report_chat_agent"


def test_approval_creation_subgraph_keeps_approval_internal_nodes() -> None:
    module = importlib.import_module("app.graph.approval_workflow")
    graph = module.create_approval_creation_workflow()

    nodes = graph.get_graph().nodes

    assert "approval_creation_entry" in nodes
    assert "load_context" in nodes
    assert "classify" in nodes
    assert "collect" in nodes
    assert "submit" in nodes


def test_studio_examples_include_minimal_new_approval_state() -> None:
    module = importlib.import_module("app.graph.studio")

    example = module.STUDIO_EXAMPLES["new_purchase"]

    assert example["session_id"] == "studio-new-purchase"
    assert example["user_message"] == "我要申请采购笔记本电脑"
    assert example["status"] == "idle"


def test_approval_tools_are_modern_langchain_core_tools() -> None:
    module = importlib.import_module("app.tools.approval_tools")

    names = {tool.name for tool in module.APPROVAL_TOOLS}

    assert {
        "search_approval_templates",
        "get_approval_form_fields",
        "get_holiday_rule_options",
        "get_related_business_options",
    }.issubset(names)
    search_tool = next(
        tool for tool in module.APPROVAL_TOOLS if tool.name == "search_approval_templates"
    )
    schema = search_tool.args_schema.model_json_schema()
    assert "keyword" in schema["properties"]

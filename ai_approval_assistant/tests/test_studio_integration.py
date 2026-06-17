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
    assert "load_context" not in graph.get_graph().nodes
    assert "collect" not in graph.get_graph().nodes


def test_approval_creation_subgraph_keeps_approval_internal_nodes() -> None:
    module = importlib.import_module("app.agents.approval_agent")
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

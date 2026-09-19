from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import patch


os.environ.setdefault("LLM_API_KEY", "static-smoke-key")
os.environ.setdefault("LLM_MODEL", "gpt-4o-mini")
os.environ.setdefault("LANGSMITH_TRACING", "false")

PROJECT_DIR = Path(__file__).resolve().parent

from deep_agent_examples import graphs  # noqa: E402
from deep_agent_examples.config import model_settings  # noqa: E402
from deep_agent_examples.lifecycle import merge_lifecycle_events  # noqa: E402
from deep_agent_examples.tools import check_budget, check_inventory  # noqa: E402


def main() -> None:
    with (
        patch("deep_agent_examples.config.load_environment"),
        patch.dict(
            os.environ,
            {
                "DEEPSEEK_API_KEY": "deepseek-test-key",
                "OPENAI_BASE_URL": "https://wrong-provider.example/v1",
                "OPENAI_MODEL": "wrong-provider-model",
            },
            clear=True,
        ),
    ):
        settings = model_settings()
        assert settings.base_url == "https://api.deepseek.com/v1"
        assert settings.model == "deepseek-chat"

    config = json.loads((PROJECT_DIR / "langgraph.json").read_text(encoding="utf-8"))
    expected = set(config["graphs"])
    exported = {
        "tool_agent",
        "lifecycle_agent",
        "subagent_lifecycle_agent",
        "subagent_agent",
        "compiled_subagent_agent",
        "remote_research_agent",
        "async_subagent_agent",
        "backend_agent",
        "dynamic_skill_agent",
        "hitl_harness_agent",
        "local_shell_agent",
    }
    assert expected == exported
    assert all(hasattr(getattr(graphs, name), "invoke") for name in exported)
    lifecycle_nodes = set(graphs.lifecycle_agent.get_graph().nodes)
    assert {
        "AgentLifecycleProbe.before_agent",
        "AgentLifecycleProbe.before_model",
        "AgentLifecycleProbe.after_model",
        "AgentLifecycleProbe.after_agent",
    } <= lifecycle_nodes
    assert "ParentLifecycleProbe.before_agent" in set(
        graphs.subagent_lifecycle_agent.get_graph().nodes
    )

    inventory = json.loads(
        check_inventory.invoke({"item": "AI 推理服务器", "quantity": 4})
    )
    budget = json.loads(check_budget.invoke({"department": "研发平台部", "amount": 272000}))
    assert inventory == {
        "available": 1,
        "enough": False,
        "item": "AI 推理服务器",
        "requested": 4,
    }
    assert budget["enough"] is False and budget["gap"] == 4000
    assert "/skills/session/procurement-review/SKILL.md" in graphs.DYNAMIC_SKILL_FILES
    assert merge_lifecycle_events(
        ["01 parent.before_agent"],
        ["01 parent.before_agent", "02 parent.before_model"],
    ) == ["01 parent.before_agent", "02 parent.before_model"]
    print(
        f"static smoke passed: {len(exported)} graphs, lifecycle hooks, "
        "deterministic tools, dynamic skill"
    )


if __name__ == "__main__":
    main()

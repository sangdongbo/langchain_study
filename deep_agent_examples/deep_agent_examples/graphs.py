from __future__ import annotations

import os
from pathlib import Path

from deepagents import (
    AsyncSubAgent,
    CompiledSubAgent,
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    SubAgent,
    create_deep_agent,
    register_harness_profile,
)
from deepagents.backends import LocalShellBackend, StateBackend
from deepagents.middleware import FilesystemPermission
from langchain.agents import create_agent
from langchain.agents.middleware import ModelCallLimitMiddleware, ToolCallLimitMiddleware
from langgraph.checkpoint.base import BaseCheckpointSaver

from deep_agent_examples.config import PROJECT_DIR, build_model, load_environment, model_settings
from deep_agent_examples.lifecycle import LifecycleProbeMiddleware, LifecycleState
from deep_agent_examples.tools import (
    PROCUREMENT_TOOLS,
    calculate_total,
    check_budget,
    check_inventory,
    check_supplier,
    publish_review,
)


load_environment()
MODEL = build_model()

# Disable the automatic general-purpose subagent so every graph shows only the
# capability under study. Explicit SubAgent examples still expose `task`.
register_harness_profile(
    f"openai:{model_settings().model}",
    HarnessProfile(
        system_prompt_suffix=(
            "Use tools for facts and calculations. Never claim that an action "
            "completed unless its tool result proves it."
        ),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)


tool_agent = create_deep_agent(
    model=MODEL,
    tools=PROCUREMENT_TOOLS,
    name="tool-agent",
    system_prompt=(
        "You are a procurement review assistant. Check total, inventory, budget, "
        "and supplier evidence before giving a Chinese recommendation."
    ),
)


lifecycle_agent = create_deep_agent(
    model=MODEL,
    tools=[calculate_total],
    middleware=[LifecycleProbeMiddleware("agent")],
    state_schema=LifecycleState,
    name="lifecycle-agent",
    system_prompt=(
        "Call calculate_total exactly once, then answer in Chinese. This graph records "
        "its lifecycle hooks in lifecycle_events."
    ),
)


lifecycle_reviewer: SubAgent = {
    "name": "lifecycle-reviewer",
    "description": "Checks inventory while exposing the child agent lifecycle.",
    "model": MODEL,
    "tools": [check_inventory],
    "middleware": [
        LifecycleProbeMiddleware("child", "child_lifecycle_events"),
    ],
    "system_prompt": (
        "Call check_inventory exactly once and return a short Chinese conclusion."
    ),
}

subagent_lifecycle_agent = create_deep_agent(
    model=MODEL,
    subagents=[lifecycle_reviewer],
    middleware=[
        LifecycleProbeMiddleware("parent", "parent_lifecycle_events"),
    ],
    state_schema=LifecycleState,
    name="subagent-lifecycle-agent",
    system_prompt=(
        "Delegate exactly once to lifecycle-reviewer, then return its conclusion. "
        "Do not perform the inventory review yourself."
    ),
)


risk_subagent: SubAgent = {
    "name": "risk-reviewer",
    "description": "Independently checks supplier, inventory, and delivery risks.",
    "model": MODEL,
    "tools": [check_inventory, check_supplier],
    "system_prompt": (
        "You are an independent risk reviewer. Use tools, list evidence, and return "
        "only risks and mitigations in Chinese."
    ),
}

subagent_agent = create_deep_agent(
    model=MODEL,
    tools=[calculate_total, check_budget],
    subagents=[risk_subagent],
    name="subagent-agent",
    system_prompt=(
        "You lead a procurement review. Check amount and budget yourself, delegate an "
        "independent risk review to risk-reviewer, then merge both conclusions."
    ),
)


finance_graph = create_agent(
    model=MODEL,
    tools=[calculate_total, check_budget],
    name="finance-review-graph",
    system_prompt=(
        "You are a reusable finance review graph. Verify the total and budget, then "
        "return a short Chinese finance conclusion."
    ),
)

finance_compiled_subagent: CompiledSubAgent = {
    "name": "finance-graph-reviewer",
    "description": "Runs a precompiled LangChain finance review graph.",
    "runnable": finance_graph,
}

compiled_subagent_agent = create_deep_agent(
    model=MODEL,
    tools=[check_inventory, check_supplier],
    subagents=[finance_compiled_subagent],
    name="compiled-subagent-agent",
    system_prompt=(
        "Check inventory and supplier risk, delegate finance verification to "
        "finance-graph-reviewer, and return one Chinese report."
    ),
)


# This graph is both directly runnable and the remote target used by the async example.
remote_research_agent = create_deep_agent(
    model=MODEL,
    tools=[check_inventory, check_supplier],
    name="remote-research-agent",
    system_prompt=(
        "You are a background procurement researcher. Gather supplier and inventory "
        "evidence and return a concise Chinese research memo."
    ),
)


def _remote_researcher() -> AsyncSubAgent:
    server_url = os.getenv("AGENT_SERVER_URL") or "http://127.0.0.1:2024"
    spec: AsyncSubAgent = {
        "name": "remote-procurement-researcher",
        "description": "Runs a long procurement investigation in the background.",
        "graph_id": "remote_research_agent",
        "url": server_url,
    }
    if token := os.getenv("AGENT_SERVER_TOKEN"):
        spec["headers"] = {"Authorization": f"Bearer {token}"}
    return spec


async_subagent_agent = create_deep_agent(
    model=MODEL,
    tools=[calculate_total, check_budget],
    subagents=[_remote_researcher()],
    name="async-subagent-agent",
    system_prompt=(
        "For requests that explicitly ask for background research, call "
        "start_async_task once and return its task_id immediately. Do not poll unless "
        "the user asks for status or results."
    ),
)


backend_agent = create_deep_agent(
    model=MODEL,
    tools=PROCUREMENT_TOOLS,
    backend=StateBackend(),
    name="state-backend-agent",
    system_prompt=(
        "Use tools to review the request, write working notes to /work/evidence.md, "
        "write the final report to /reports/review.md, then tell the user both paths."
    ),
)


SKILL_FILE = PROJECT_DIR / "skills" / "procurement-review" / "SKILL.md"
DYNAMIC_SKILL_FILES = {
    "/skills/session/procurement-review/SKILL.md": {
        "content": SKILL_FILE.read_text(encoding="utf-8"),
        "encoding": "utf-8",
    }
}

dynamic_skill_agent = create_deep_agent(
    model=MODEL,
    tools=PROCUREMENT_TOOLS,
    backend=StateBackend(),
    skills=["/skills/session/"],
    name="dynamic-skill-agent",
    system_prompt=(
        "Discover the session skill before reviewing the request. Follow its procedure "
        "and say which skill you used."
    ),
)


HITL_PERMISSIONS = [
    FilesystemPermission(
        operations=["write"],
        paths=["/reports/drafts/**"],
        mode="allow",
    ),
    FilesystemPermission(
        operations=["write"],
        paths=["/reports/final/**"],
        mode="interrupt",
    ),
    FilesystemPermission(
        operations=["write"],
        paths=["/**"],
        mode="deny",
    ),
]


def build_hitl_harness_agent(
    checkpointer: BaseCheckpointSaver | None = None,
):
    return create_deep_agent(
        model=MODEL,
        tools=[*PROCUREMENT_TOOLS, publish_review],
        backend=StateBackend(),
        permissions=HITL_PERMISSIONS,
        interrupt_on={"publish_review": True},
        middleware=[
            ModelCallLimitMiddleware(run_limit=12, exit_behavior="error"),
            ToolCallLimitMiddleware(run_limit=20, exit_behavior="error"),
        ],
        checkpointer=checkpointer,
        name="hitl-harness-agent",
        system_prompt=(
            "Review with deterministic tools, write a draft to "
            "/reports/drafts/review.md, and call publish_review only after the draft is "
            "complete. Writing final files and publishing require human approval."
        ),
    )


# LangGraph Server supplies persistence for Studio, so exported graphs do not
# embed an in-memory checkpointer. The CLI builder adds one when it must resume.
hitl_harness_agent = build_hitl_harness_agent()


WORKSPACE_DIR = PROJECT_DIR / "workspace"


def _safe_local_env() -> dict[str, str]:
    allowed = ("PATH", "SYSTEMROOT", "COMSPEC", "PYTHONIOENCODING")
    return {name: os.environ[name] for name in allowed if name in os.environ}


def build_local_shell_agent(
    checkpointer: BaseCheckpointSaver | None = None,
):
    backend = LocalShellBackend(
        root_dir=Path(WORKSPACE_DIR),
        virtual_mode=True,
        timeout=30,
        max_output_bytes=20_000,
        env=_safe_local_env(),
        inherit_env=False,
    )
    return create_deep_agent(
        model=MODEL,
        backend=backend,
        # deepagents 0.7.x intentionally rejects FilesystemPermission with an
        # executable backend. Shell commands could bypass path rules, so every
        # mutating file operation and command is reviewed through HITL instead.
        interrupt_on={
            "write_file": True,
            "edit_file": True,
            "delete": True,
            "execute": True,
        },
        checkpointer=checkpointer,
        name="local-shell-agent",
        system_prompt=(
            "This is a local development demonstration. Work only inside the current "
            "workspace, write files only below /artifacts, never use the network, and "
            "request approval before execute."
        ),
    )


local_shell_agent = build_local_shell_agent()

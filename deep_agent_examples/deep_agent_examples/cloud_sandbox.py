from __future__ import annotations

import os

from deepagents import create_deep_agent
from deepagents.backends import LangSmithSandbox
from langsmith import tracing_context
from langsmith.sandbox import SandboxClient

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    load_environment,
    tracing_enabled,
    tracing_project,
)


def run_langsmith_sandbox(prompt: str, thread_id: str = "cloud-sandbox-demo") -> dict:
    """Create one disposable LangSmith cloud sandbox and trace the agent run."""
    load_environment()
    if not os.getenv("LANGSMITH_API_KEY"):
        raise RuntimeError("LANGSMITH_API_KEY is required for LangSmith Sandbox.")

    sandbox_kwargs = {
        "idle_ttl_seconds": 600,
        "delete_after_stop_seconds": 600,
    }
    if snapshot_name := os.getenv("LANGSMITH_SANDBOX_SNAPSHOT"):
        sandbox_kwargs["snapshot_name"] = snapshot_name

    client = SandboxClient()
    with client.sandbox(**sandbox_kwargs) as sandbox:
        agent = create_deep_agent(
            model=build_model(),
            backend=LangSmithSandbox(sandbox),
            name="langsmith-sandbox-agent",
            system_prompt=(
                "Work only inside the disposable cloud sandbox. Create files under "
                "/workspace and report command exit codes and artifact paths."
            ),
        )
        with tracing_context(
            enabled=tracing_enabled(),
            project_name=tracing_project(),
            tags=["deep-agent-example", "langsmith-sandbox"],
            metadata={"example": "langsmith-sandbox"},
        ):
            return agent.invoke(
                {"messages": [{"role": "user", "content": prompt}]},
                config=invoke_config("langsmith-sandbox", thread_id),
            )

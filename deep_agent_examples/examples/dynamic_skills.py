"""Run the State-backed Skill example with optional LangSmith tracing.

Run from the deep_agent_examples directory:
    uv run python examples/dynamic_skills.py
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from uuid import uuid4

from langsmith import tracing_context

from deep_agent_examples.config import (
    PROJECT_DIR,
    invoke_config,
    tracing_enabled,
    tracing_project,
)


DEFAULT_PROMPT = (
    "按本会话的采购评审技能，评审研发平台部采购 4 台 AI 推理服务器，"
    "单价 68000 元，供应商北辰智能硬件。"
)

TASK_PROMPTS = {
    "purchase": DEFAULT_PROMPT,
    "supplier-risk": "调查北辰智能硬件供应商和 AI 推理服务器库存风险。",
}

ROLE_SKILLS = {
    "buyer": {"procurement-review"},
    "risk-reviewer": {"procurement-review", "supplier-research"},
}

TASK_SKILLS = {
    "purchase": {"procurement-review"},
    "supplier-risk": {"supplier-research"},
}


@dataclass(frozen=True)
class TrustedIdentity:
    tenant_id: str
    role: str


def skill_files_for(identity: TrustedIdentity, task_type: str) -> dict:
    """Return only Skills allowed by both the trusted role and task policy."""
    selected = ROLE_SKILLS.get(identity.role, set()) & TASK_SKILLS.get(task_type, set())
    if not selected:
        raise PermissionError(
            f"Role {identity.role!r} cannot use a Skill for task {task_type!r}."
        )
    return {
        f"/skills/session/{name}/SKILL.md": {
            "content": (PROJECT_DIR / "skills" / name / "SKILL.md").read_text(
                encoding="utf-8"
            ),
            "encoding": "utf-8",
        }
        for name in sorted(selected)
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run a State-backed Dynamic Skill and trace it in LangSmith."
    )
    parser.add_argument("--prompt", help="Override the task-type default prompt.")
    parser.add_argument(
        "--role",
        choices=sorted(ROLE_SKILLS),
        default="buyer",
        help="Simulates a server-authenticated role for this local example.",
    )
    parser.add_argument(
        "--task-type",
        choices=sorted(TASK_SKILLS),
        default="purchase",
    )
    parser.add_argument(
        "--thread-id",
        default=f"dynamic-skill-{uuid4().hex[:8]}",
        help="Use a new ID when changing the Skill bundle.",
    )
    args = parser.parse_args()

    # In production, construct this only from authenticated server Context.
    # Never authorize a role copied directly from user text or model State.
    identity = TrustedIdentity(tenant_id="tenant-a", role=args.role)
    skill_files = skill_files_for(identity, args.task_type)
    selected_skills = [path.split("/")[-2] for path in skill_files]

    # Construct the configured real model only after the deterministic policy
    # accepts the request, so denied routes never reach model initialization.
    from deep_agent_examples.graphs import dynamic_skill_agent

    config = invoke_config("dynamic-skills-py", args.thread_id)
    config["metadata"].update(
        {
            "entrypoint": "examples/dynamic_skills.py",
            "tenant_id": identity.tenant_id,
            "role": identity.role,
            "task_type": args.task_type,
            "skill_bundle": ",".join(selected_skills),
        }
    )

    trace_on = tracing_enabled()
    with tracing_context(
        enabled=trace_on,
        project_name=tracing_project(),
        tags=["deep-agent-example", "dynamic-skills", "python-file"],
        metadata=config["metadata"],
    ):
        result = dynamic_skill_agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": args.prompt or TASK_PROMPTS[args.task_type],
                    }
                ],
                "files": skill_files,
            },
            config=config,
        )

    print(result["messages"][-1].content)
    print(f"\nthread_id: {args.thread_id}")
    print(f"selected Skills: {', '.join(selected_skills)}")
    if trace_on:
        print(f"LangSmith project: {tracing_project()}")
    else:
        print("LangSmith tracing disabled; set LANGSMITH_TRACING=true to enable it.")


if __name__ == "__main__":
    main()

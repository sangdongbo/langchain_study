"""按 thread 注入不同 Skill 版本的真实模型示例。

运行命令：
    uv run python examples/skill_versioning/run.py --version v1
    uv run python examples/skill_versioning/run.py --version v2
"""

from __future__ import annotations

import argparse
from uuid import uuid4

from deepagents import create_deep_agent
from deepagents.backends import StateBackend
from langgraph.checkpoint.memory import InMemorySaver
from langsmith import tracing_context

from deep_agent_examples.config import (
    build_model,
    invoke_config,
    tracing_enabled,
    tracing_project,
)
from deep_agent_examples.tools import PROCUREMENT_TOOLS


# 两个版本使用相同 Skill 名和虚拟路径，仅 frontmatter 版本与流程不同，
# 用来演示版本选择是 thread 级状态，而不是全局替换。
SKILLS = {
    "v1": """---
name: procurement-review
description: Review amount and budget for a purchase
metadata:
  version: "v1"
---

# Procurement Review v1

1. Use calculate_total.
2. Use check_budget.
3. Return a Chinese finance recommendation and state that Skill v1 was used.
""",
    "v2": """---
name: procurement-review
description: Review amount, budget, inventory, and supplier risk
metadata:
  version: "v2"
---

# Procurement Review v2

1. Use calculate_total.
2. Use check_budget, check_inventory, and check_supplier.
3. Return a Chinese evidence table and state that Skill v2 was used.
""",
}


def skill_files(version: str) -> dict:
    """把指定版本放到稳定虚拟路径中，供当前 thread 的 Middleware 扫描。"""
    return {
        "/skills/session/procurement-review/SKILL.md": {
            "content": SKILLS[version],
            "encoding": "utf-8",
        }
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="演示 thread 级 Skill 版本选择。")
    parser.add_argument("--version", choices=sorted(SKILLS), default="v2")
    parser.add_argument("--thread-id")
    args = parser.parse_args()
    thread_id = args.thread_id or f"skill-{args.version}-{uuid4().hex[:8]}"

    # StateBackend 保存虚拟 Skill 文件，Checkpointer 保存当前 thread 首次扫描的
    # skills_metadata；同一个 thread 不应用来切换 Skill 版本。
    checkpointer = InMemorySaver()
    agent = create_deep_agent(
        model=build_model(),
        tools=PROCUREMENT_TOOLS,
        backend=StateBackend(),
        skills=["/skills/session/"],
        checkpointer=checkpointer,
        name="skill-versioning-agent",
        system_prompt="先读取当前 thread 提供的采购 Skill，再严格按其版本执行。",
    )
    config = invoke_config("skill-versioning", thread_id)
    config["metadata"]["skill_version"] = args.version

    with tracing_context(
        enabled=tracing_enabled(),
        project_name=tracing_project(),
        tags=["deep-agent-example", "skill-versioning", args.version],
        metadata=config["metadata"],
    ):
        # 首次调用把选定版本写入 State，SkillsMiddleware 随后扫描固定虚拟目录。
        result = agent.invoke(
            {
                "messages": [
                    {
                        "role": "user",
                        "content": (
                            "评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，"
                            "供应商北辰智能硬件。"
                        ),
                    }
                ],
                "files": skill_files(args.version),
            },
            config=config,
        )

    # 直接读取 checkpointed State，确认 Middleware 实际识别到的版本。
    metadata = agent.get_state(config).values.get("skills_metadata") or []
    print(result["messages"][-1].content)
    print(f"thread_id: {thread_id}")
    print(f"skills_metadata: {metadata}")


if __name__ == "__main__":
    main()

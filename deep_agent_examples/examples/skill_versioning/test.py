"""Skill 版本与 thread metadata 缓存离线测试。

运行命令：
    uv run python examples/skill_versioning/test.py
"""

from __future__ import annotations

import os
from typing import Any

# 版本缓存测试全部使用内存 State 和 Fake Model。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import StateBackend  # noqa: E402
from langchain_core.messages import AIMessage, SystemMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


def skill_files(version: str) -> dict:
    # 两个版本故意共用同一个虚拟路径，才能验证同 thread 的 metadata 缓存。
    return {
        "/skills/session/procurement-review/SKILL.md": {
            "content": f"""---
name: procurement-review
description: Procurement review procedure {version}
metadata:
  version: "{version}"
---

# Procedure {version}

Use the {version} procedure.
""",
            "encoding": "utf-8",
        }
    }


def _system_text(messages: list[Any]) -> str:
    return "\n".join(
        str(message.content)
        for message in messages
        if isinstance(message, SystemMessage)
    )


def main() -> None:
    configure_utf8_output()
    # 三条响应依次对应 v1 首次调用、同 thread 覆盖、全新 v2 thread。
    model = ToolCapableFakeModel(
        responses=[
            AIMessage(content="thread v1 complete"),
            AIMessage(content="same thread complete"),
            AIMessage(content="thread v2 complete"),
        ]
    )
    checkpointer = InMemorySaver()
    agent = create_deep_agent(
        model=model,
        backend=StateBackend(),
        skills=["/skills/session/"],
        checkpointer=checkpointer,
        name="skill-versioning-test-agent",
    )
    v1_config = {"configurable": {"thread_id": "skill-version-v1"}}
    v2_config = {"configurable": {"thread_id": "skill-version-v2"}}

    # v1 thread 首次扫描并缓存 frontmatter metadata。
    agent.invoke(
        {
            "messages": [{"role": "user", "content": "first request"}],
            "files": skill_files("v1"),
        },
        config=v1_config,
    )
    v1_metadata = agent.get_state(v1_config).values["skills_metadata"]
    assert v1_metadata[0]["metadata"]["version"] == "v1"
    assert "procedure v1" in _system_text(model.seen_messages[0])

    # 同一 thread 即使覆盖虚拟文件，SkillsMiddleware 仍复用首次扫描的 metadata。
    agent.invoke(
        {
            "messages": [{"role": "user", "content": "replace with v2"}],
            "files": skill_files("v2"),
        },
        config=v1_config,
    )
    cached_metadata = agent.get_state(v1_config).values["skills_metadata"]
    assert cached_metadata[0]["metadata"]["version"] == "v1"
    assert "procedure v1" in _system_text(model.seen_messages[1])

    # 新 thread 首次扫描新的 files，因此能得到 v2 metadata。
    agent.invoke(
        {
            "messages": [{"role": "user", "content": "new v2 thread"}],
            "files": skill_files("v2"),
        },
        config=v2_config,
    )
    v2_metadata = agent.get_state(v2_config).values["skills_metadata"]
    assert v2_metadata[0]["metadata"]["version"] == "v2"
    assert "procedure v2" in _system_text(model.seen_messages[2])

    print("Skill 版本管理离线测试通过")
    print("- frontmatter metadata 正确保存版本")
    print("- 同一 thread 保留首次扫描的 Skill metadata")
    print("- 新 thread 可以安全切换到新版本")


if __name__ == "__main__":
    main()

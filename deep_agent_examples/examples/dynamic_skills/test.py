"""动态 Skills 离线测试，使用 Fake Model，不访问真实模型或 LangSmith。

运行命令：
    uv run python examples/dynamic_skills/test.py

预期结果：
    输出“动态 Skills 离线测试通过”，并验证权限路由、metadata 注入和 thread 缓存。
"""

from __future__ import annotations

import os
from typing import Any

# 强制关闭外部 tracing，确保测试完全离线。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import create_deep_agent  # noqa: E402
from deepagents.backends import StateBackend  # noqa: E402
from langchain_core.messages import AIMessage, SystemMessage, ToolMessage  # noqa: E402
from langgraph.checkpoint.memory import InMemorySaver  # noqa: E402

from run import TrustedIdentity, skill_files_for  # noqa: E402
from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


# 两份最小 Skill 内容分别用于首次扫描和同 thread 覆盖场景。
PROCUREMENT_SKILL = """---
name: procurement-review
description: Review purchases using deterministic evidence
---

# Procurement Review

1. Read the request.
2. Check deterministic evidence.
3. Return a recommendation.
"""

SUPPLIER_SKILL = """---
name: supplier-research
description: Research supplier delivery risk
---

# Supplier Research

Check supplier delivery evidence.
"""


def _read_skill_call(call_id: str) -> AIMessage:
    # 模拟模型按需读取完整 Skill 正文，而不是让正文默认进入 system prompt。
    return AIMessage(
        # 空 content 表示本轮只调用 read_file，不输出最终文本。
        content="",
        tool_calls=[
            {
                # SkillsMiddleware 通过 Backend 自动提供 read_file 工具。
                "name": "read_file",
                "args": {
                    # file_path 是 StateBackend 中的虚拟路径，不是本机文件路径。
                    "file_path": "/skills/session/procurement-review/SKILL.md",
                    # limit：本次最多读取 1000 行，用于大文件分页和控制上下文大小。
                    "limit": 1000,
                },
                # id 用于关联 read_file 返回的 ToolMessage。
                "id": call_id,
            }
        ],
    )


def _system_text(messages: list[Any]) -> str:
    return "\n".join(
        str(message.content)
        for message in messages
        if isinstance(message, SystemMessage)
    )


def main() -> None:
    configure_utf8_output()

    # 先验证确定性权限路由：risk-reviewer 可以调查供应商，buyer 不可以。
    routed = skill_files_for(
        TrustedIdentity(tenant_id="tenant-a", role="risk-reviewer"),
        "supplier-risk",
    )
    assert set(routed) == {"/skills/session/supplier-research/SKILL.md"}
    try:
        skill_files_for(
            TrustedIdentity(tenant_id="tenant-a", role="buyer"),
            "supplier-risk",
        )
    except PermissionError:
        pass
    else:
        raise AssertionError("buyer must not receive supplier-research")

    # 两轮都尝试 read_file；用于同时检查渐进式披露和 metadata 缓存。
    model = ToolCapableFakeModel(
        responses=[
            _read_skill_call("read-skill-1"),
            AIMessage(content="first run complete"),
            _read_skill_call("read-skill-2"),
            AIMessage(content="second run complete"),
        ]
    )
    agent = create_deep_agent(
        # model：预制两轮 read_file 调用，测试不访问真实模型。
        model=model,
        # backend：让 Skill 文件存在 Graph State 的 files 字段中。
        backend=StateBackend(),
        # skills：扫描虚拟目录下的 */SKILL.md，并先注入其 metadata。
        skills=["/skills/session/"],
        # checkpointer：按 thread_id 缓存首次扫描的 skills_metadata。
        checkpointer=InMemorySaver(),
        # 测试 Graph 的名称。
        name="dynamic-skills-test-agent",
    )
    config = {"configurable": {"thread_id": "dynamic-skills-test"}}

    # 首次调用扫描采购 Skill：system prompt 只有 metadata，正文由 read_file 返回。
    first = agent.invoke(
        {
            "messages": [{"role": "user", "content": "Review this purchase."}],
            "files": {
                "/skills/session/procurement-review/SKILL.md": {
                    "content": PROCUREMENT_SKILL,
                    "encoding": "utf-8",
                }
            },
        },
        config=config,
    )
    first_state = agent.get_state(config).values
    assert first["messages"][-1].content == "first run complete"
    assert [item["name"] for item in first_state["skills_metadata"]] == [
        "procurement-review"
    ]
    assert "procurement-review" in _system_text(model.seen_messages[0])
    assert "# Procurement Review" not in _system_text(model.seen_messages[0])
    assert any(
        isinstance(message, ToolMessage) and "# Procurement Review" in message.text
        for message in model.seen_messages[1]
    )

    # 同一 thread 再注入供应商 Skill 文件，文件会进入 State，但首次扫描的
    # skills_metadata 仍被缓存，不会自动切换能力集合。
    second = agent.invoke(
        {
            "messages": [{"role": "user", "content": "Now research the supplier."}],
            "files": {
                "/skills/session/supplier-research/SKILL.md": {
                    "content": SUPPLIER_SKILL,
                    "encoding": "utf-8",
                }
            },
        },
        config=config,
    )
    second_state = agent.get_state(config).values
    assert second["messages"][-1].content == "second run complete"
    assert "/skills/session/supplier-research/SKILL.md" in second_state["files"]
    assert [item["name"] for item in second_state["skills_metadata"]] == [
        "procurement-review"
    ]
    assert all(
        "supplier-research" not in _system_text(messages)
        for messages in model.seen_messages[2:]
    )

    print("动态 Skills 离线测试通过")
    print("- 可信角色和任务路由会正确允许或拒绝 Skill 集合")
    print("- metadata 会在第一次模型调用前注入")
    print("- 完整 SKILL.md 只会在 read_file 后进入消息")
    print("- 同一 thread 添加其他 Skill 文件后仍使用已缓存的 metadata")


if __name__ == "__main__":
    main()

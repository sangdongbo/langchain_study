"""动态 Skills 真实演示：根据可信身份和任务类型选择 State Skill。

运行条件：
    在 deep_agent_examples 目录配置模型 API Key。

运行命令：
    uv run python examples/dynamic_skills/run.py

预期结果：
    输出模型评审结果、thread_id、选中的 Skills，以及 LangSmith tracing 是否启用。

离线测试：
    uv run python examples/dynamic_skills/test.py
    测试通过时输出“动态 Skills 离线测试通过”。
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

# 身份能使用哪些 Skill，由服务端可信角色决定。
ROLE_SKILLS = {
    "buyer": {"procurement-review"},
    "risk-reviewer": {"procurement-review", "supplier-research"},
}

# 当前业务任务允许哪些 Skill，防止角色权限被用于无关场景。
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
    # 必须同时满足角色权限和任务策略；客户端文本不能直接指定任意 Skill。
    selected = ROLE_SKILLS.get(identity.role, set()) & TASK_SKILLS.get(task_type, set())
    if not selected:
        raise PermissionError(
            f"Role {identity.role!r} cannot use a Skill for task {task_type!r}."
        )
    # StateBackend 使用虚拟绝对路径保存文件。Middleware 先扫描 frontmatter，
    # 模型真正需要正文时再调用 read_file，实现渐进式披露。
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

    # 生产环境只能从已认证的服务端 Context 构造身份，不能信任用户文本
    # 或模型 State 中自行声明的 role。
    identity = TrustedIdentity(tenant_id="tenant-a", role=args.role)
    skill_files = skill_files_for(identity, args.task_type)
    selected_skills = [path.split("/")[-2] for path in skill_files]

    # 确定性策略通过后才导入并构建真实模型，让无权限请求止步于模型调用之前。
    from deep_agent_examples.graphs import dynamic_skill_agent

    # 把可信身份、任务类型和最终 Skill 集合写入 trace，方便审计路由结果。
    config = invoke_config("dynamic-skills-py", args.thread_id)
    config["metadata"].update(
        {
            "entrypoint": "examples/dynamic_skills/run.py",
            "tenant_id": identity.tenant_id,
            "role": identity.role,
            "task_type": args.task_type,
            "skill_bundle": ",".join(selected_skills),
        }
    )

    trace_on = tracing_enabled()
    with tracing_context(
        # enabled：只开关 LangSmith 追踪，不影响 Skill 选择和读取。
        enabled=trace_on,
        # project_name：Trace 在 LangSmith 中归属的项目。
        project_name=tracing_project(),
        # tags：用于筛选动态 Skill 示例，不传给模型。
        tags=["deep-agent-example", "dynamic-skills", "python-file"],
        # metadata：记录可信身份和路由结果，便于审计，但不进入模型上下文。
        metadata=config["metadata"],
    ):
        # files 随本次 thread 注入 State；同一 thread 的 skills_metadata
        # 会缓存首次扫描结果，切换 Skill 集合时应使用新的 thread_id。
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
            # config 中的 thread_id 决定 Skills metadata 缓存属于哪个会话。
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

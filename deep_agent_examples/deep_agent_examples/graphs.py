"""集中定义可由 CLI 和 LangGraph Studio 运行的示例 Graph。

``create_deep_agent`` 会根据 model、tools、middleware、subagents、backend 等参数
自动组装 LangGraph 节点和边。因此 Studio 中看到的 ``model``、``tools``、
``*.before_agent`` 等节点来自框架编译结果，并不是本文件手工绘制的流程图。
"""

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


# 先加载 .env，再创建供本文件所有 Graph 共用的模型实例。
load_environment()
MODEL = build_model()

# 关闭框架自动提供的通用子 Agent，让每张示例图只展示当前主题相关的能力。
# 显式配置了 SubAgent 的示例仍会获得 task 工具，用它把任务委派给指定子 Agent。
register_harness_profile(
    # Profile 按“模型提供方:模型名”注册，只作用于当前示例所用模型。
    f"openai:{model_settings().model}",
    HarnessProfile(
        # 所有示例共享的附加提示：事实和计算必须来自工具，不能虚构执行成功。
        system_prompt_suffix=(
            "Use tools for facts and calculations. Never claim that an action "
            "completed unless its tool result proves it."
        ),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)


# 最基础的工具调用示例：模型可在采购评审过程中自主选择确定性工具。
# create_deep_agent 会据此生成 model <-> tools 循环，直到模型输出最终答案。
tool_agent = create_deep_agent(
    # 所有推理轮次使用的聊天模型。
    model=MODEL,
    # 注册 calculate_total、check_inventory、check_budget、check_supplier。
    tools=PROCUREMENT_TOOLS,
    # Graph/Studio/追踪中使用的稳定名称。
    name="tool-agent",
    # 业务层提示词约束评审步骤和最终回答语言。
    system_prompt=(
        "You are a procurement review assistant. Check total, inventory, budget, "
        "and supplier evidence before giving a Chinese recommendation."
    ),
)


# 生命周期示例：只提供一个计算工具，并插入自定义 Middleware 记录每个钩子。
lifecycle_agent = create_deep_agent(
    model=MODEL,
    tools=[calculate_total],
    # scope="agent" 会生成 agent.before_model 等事件并写入 lifecycle_events。
    middleware=[LifecycleProbeMiddleware("agent")],
    # Graph State 必须声明 Middleware 新增的生命周期字段及其 reducer。
    state_schema=LifecycleState,
    name="lifecycle-agent",
    system_prompt=(
        "Call calculate_total exactly once, then answer in Chinese. This graph records "
        "its lifecycle hooks in lifecycle_events."
    ),
)


# 声明式子 Agent 配置本身是普通字典，由父 Agent 创建时编译成可委派目标。
lifecycle_reviewer: SubAgent = {
    # name 是父 Agent 调用 task 工具时使用的目标名称。
    "name": "lifecycle-reviewer",
    # description 帮助父模型判断什么任务适合委派给它。
    "description": "Checks inventory while exposing the child agent lifecycle.",
    "model": MODEL,
    # 子 Agent 权限最小化，只允许查询库存。
    "tools": [check_inventory],
    "middleware": [
        # 子 Agent 的钩子写入独立字段，避免与父 Agent 事件混在一起。
        LifecycleProbeMiddleware("child", "child_lifecycle_events"),
    ],
    "system_prompt": (
        "Call check_inventory exactly once and return a short Chinese conclusion."
    ),
}

# 父子生命周期示例：父 Agent 通过自动生成的 task 工具调用 lifecycle_reviewer。
subagent_lifecycle_agent = create_deep_agent(
    model=MODEL,
    subagents=[lifecycle_reviewer],
    middleware=[
        # 父 Agent 使用另一字段记录自己的生命周期。
        LifecycleProbeMiddleware("parent", "parent_lifecycle_events"),
    ],
    state_schema=LifecycleState,
    name="subagent-lifecycle-agent",
    system_prompt=(
        "Delegate exactly once to lifecycle-reviewer, then return its conclusion. "
        "Do not perform the inventory review yourself."
    ),
)


# 常规声明式风险子 Agent：独立检查库存和供应商，不接触金额与预算工具。
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

# 父 Agent 自己核算金额/预算，再把风险检查委派出去，最后合并两部分结论。
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


# 先用 LangChain create_agent 创建一张可独立运行的财务审核图。
finance_graph = create_agent(
    model=MODEL,
    tools=[calculate_total, check_budget],
    name="finance-review-graph",
    system_prompt=(
        "You are a reusable finance review graph. Verify the total and budget, then "
        "return a short Chinese finance conclusion."
    ),
)

# CompiledSubAgent 不重新声明 model/tools，而是直接复用已经编译好的 Runnable 图。
finance_compiled_subagent: CompiledSubAgent = {
    "name": "finance-graph-reviewer",
    "description": "Runs a precompiled LangChain finance review graph.",
    "runnable": finance_graph,
}

# 编译式子 Agent 示例：父 Agent 负责供应商/库存，财务部分委派给 finance_graph。
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


# 这张图既能在 Studio 中独立运行，也是异步子 Agent 示例调用的远程目标。
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
    """根据环境变量生成异步远程子 Agent 描述。

    父 Agent 不在当前进程直接执行该图，而是通过 LangGraph Server URL 启动
    后台任务；服务需要鉴权时再附加 Bearer Token 请求头。
    """
    # 本地 langgraph dev 默认监听 2024；生产环境通过变量覆盖。
    server_url = os.getenv("AGENT_SERVER_URL") or "http://127.0.0.1:2024"
    spec: AsyncSubAgent = {
        "name": "remote-procurement-researcher",
        "description": "Runs a long procurement investigation in the background.",
        "graph_id": "remote_research_agent",
        "url": server_url,
    }
    # 没有配置 Token 时不发送 Authorization 头，适配本地无鉴权服务。
    if token := os.getenv("AGENT_SERVER_TOKEN"):
        spec["headers"] = {"Authorization": f"Bearer {token}"}
    return spec


# 异步委派示例：start_async_task 立即返回 task_id，不在当前 run 内等待远程结果。
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


# StateBackend 文件示例：Agent 可把分析过程和报告写入 Graph State 的 files 字段。
# 这些 /work、/reports 路径都是虚拟路径，不会直接写入本机磁盘。
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


# 项目中真实存在的技能说明文件，用作本地 CLI/Studio 演示的数据来源。
SKILL_FILE = PROJECT_DIR / "skills" / "procurement-review" / "SKILL.md"

# 预构造要注入 state["files"] 的虚拟技能文件。
# 注意：定义这个常量不会自动加载技能，调用方仍需把它作为 files 输入传给 Graph。
DYNAMIC_SKILL_FILES = {
    # key 是 StateBackend 中的虚拟路径，不是 Windows 文件系统路径。
    # SkillsMiddleware 会在 /skills/session/ 下寻找“子目录/SKILL.md”。
    "/skills/session/procurement-review/SKILL.md": {
        # content 来自仓库里的真实文件，但运行时保存在当前 thread 的 State 中。
        "content": SKILL_FILE.read_text(encoding="utf-8"),
        # encoding 是 StateBackend 文件结构的一部分，确保中文内容按 UTF-8 处理。
        "encoding": "utf-8",
    }
}

# 动态技能示例：技能集合由调用方在每个 thread 的 files State 中提供。
# create_deep_agent 会因为 skills 参数自动安装 SkillsMiddleware，并在模型前增加
# SkillsMiddleware.before_agent；完整技能正文仍需模型调用 read_file 后才进入上下文。
dynamic_skill_agent = create_deep_agent(
    # 负责根据 Skill metadata 判断是否需要读取技能，并按技能步骤完成任务。
    model=MODEL,
    # Skill 规定“应该怎样评审”，真正的库存/预算等事实仍由这些工具提供。
    tools=PROCUREMENT_TOOLS,
    # StateBackend 让 SkillsMiddleware 和 read_file 访问 state["files"] 虚拟文件。
    # 未配置 checkpointer 时文件只在本次执行有效；配置后可按 thread_id 恢复。
    backend=StateBackend(),
    # 这是技能扫描根目录配置，不是要直接加载的单个 SKILL.md 文件路径。
    skills=["/skills/session/"],
    # 用于 LangGraph Studio 的 Graph 名称以及 LangSmith 追踪标识。
    name="dynamic-skill-agent",
    # 提醒模型先发现/读取会话技能，并在结果中说明实际采用了哪个技能。
    system_prompt=(
        "Discover the session skill before reviewing the request. Follow its procedure "
        "and say which skill you used."
    ),
)


# 虚拟文件系统权限按顺序匹配：允许草稿、最终报告需人工批准，其余写入拒绝。
HITL_PERMISSIONS = [
    # 草稿目录允许直接写入，不触发中断。
    FilesystemPermission(
        operations=["write"],
        paths=["/reports/drafts/**"],
        mode="allow",
    ),
    # 最终报告目录的写入会产生 interrupt，等待调用方给出批准/拒绝决定。
    FilesystemPermission(
        operations=["write"],
        paths=["/reports/final/**"],
        mode="interrupt",
    ),
    # 兜底拒绝所有其他路径，防止 Agent 写出约定目录。
    FilesystemPermission(
        operations=["write"],
        paths=["/**"],
        mode="deny",
    ),
]


def build_hitl_harness_agent(
    checkpointer: BaseCheckpointSaver | None = None,
):
    """创建带文件权限、工具审批和调用次数上限的 HITL Agent。

    传入 checkpointer 后，Graph 才能在人工审批中断后凭同一 thread_id 恢复；
    Studio 由 LangGraph Server 提供持久化，因此模块级导出时可以传空。
    """
    return create_deep_agent(
        model=MODEL,
        tools=[*PROCUREMENT_TOOLS, publish_review],
        backend=StateBackend(),
        # 控制虚拟文件写操作是允许、拒绝还是中断等待人工确认。
        permissions=HITL_PERMISSIONS,
        # publish_review 属于有外部效果的动作，每次调用都必须人工批准。
        interrupt_on={"publish_review": True},
        middleware=[
            # 限制模型和工具循环次数，配置错误时尽快失败而不是无限运行。
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


# LangGraph Server 会为 Studio 提供持久化，因此模块导出的 Graph 不内置内存
# checkpointer；CLI 需要处理中断恢复时，会通过 builder 显式传入 InMemorySaver。
hitl_harness_agent = build_hitl_harness_agent()


# LocalShellBackend 的真实工作根目录；virtual_mode 会把 Graph 内路径映射到这里。
WORKSPACE_DIR = PROJECT_DIR / "workspace"


def _safe_local_env() -> dict[str, str]:
    """只向本地 shell 子进程透传运行 Python 所需的最小环境变量集合。"""
    allowed = ("PATH", "SYSTEMROOT", "COMSPEC", "PYTHONIOENCODING")
    return {name: os.environ[name] for name in allowed if name in os.environ}


def build_local_shell_agent(
    checkpointer: BaseCheckpointSaver | None = None,
):
    """创建限制在项目 workspace 中、所有变更和命令均需审批的本地 Agent。"""
    backend = LocalShellBackend(
        # Agent 的 / 路径映射到这个目录，避免直接暴露整个本机文件系统。
        root_dir=Path(WORKSPACE_DIR),
        virtual_mode=True,
        # 限制单条命令运行时间及回传输出大小，避免失控进程和超大上下文。
        timeout=30,
        max_output_bytes=20_000,
        # 不继承完整父进程环境，防止密钥等无关变量进入 shell。
        env=_safe_local_env(),
        inherit_env=False,
    )
    return create_deep_agent(
        model=MODEL,
        backend=backend,
        # deepagents 0.7.x 不允许可执行 Backend 配合 FilesystemPermission：shell
        # 命令可能绕过路径规则，所以这里让所有文件变更和命令统一进入 HITL 审批。
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


# Studio 使用的模块级 Graph；CLI 需要恢复审批时会调用 builder 创建带 saver 的实例。
local_shell_agent = build_local_shell_agent()

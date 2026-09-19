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
        # enabled=False：不自动附带通用子 Agent，只保留每个示例显式声明的目标。
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
    # model：执行这张 Graph 中每一轮推理的聊天模型。
    model=MODEL,
    # tools：暴露给模型的工具白名单；这里仅允许调用总额计算工具。
    tools=[calculate_total],
    # scope="agent" 会生成 agent.before_model 等事件并写入 lifecycle_events。
    middleware=[LifecycleProbeMiddleware("agent")],
    # Graph State 必须声明 Middleware 新增的生命周期字段及其 reducer。
    state_schema=LifecycleState,
    # name：Graph/Studio/Trace 中的稳定标识，不是模型名称。
    name="lifecycle-agent",
    # system_prompt：只约束当前 Agent 的行为，不会自动改写工具实现。
    system_prompt=(
        "Call calculate_total exactly once, then answer in Chinese. This graph records "
        "its lifecycle hooks in lifecycle_events."
    ),
)


# 声明式子 Agent 配置本身是普通字典，由父 Agent 创建时编译成可委派目标。
lifecycle_reviewer: SubAgent = {
    # name：子 Agent 的唯一路由名；父模型调用 task 时用它选择目标。
    "name": "lifecycle-reviewer",
    # description：展示给父模型的能力说明，直接影响父模型是否决定委派。
    "description": "Checks inventory while exposing the child agent lifecycle.",
    # model：只供这个子 Agent 推理；它可以与父 Agent 使用不同模型。
    "model": MODEL,
    # tools：子 Agent 自己可调用的工具白名单，不会自动继承父 Agent 工具。
    "tools": [check_inventory],
    # middleware：只包裹子 Agent 的执行循环，不会安装到父 Agent。
    "middleware": [
        # 子 Agent 的钩子写入独立字段，避免与父 Agent 事件混在一起。
        LifecycleProbeMiddleware("child", "child_lifecycle_events"),
    ],
    # system_prompt：子 Agent 的独立角色和执行规则，不会替换父提示词。
    "system_prompt": (
        "Call check_inventory exactly once and return a short Chinese conclusion."
    ),
}

# 父子生命周期示例：父 Agent 通过自动生成的 task 工具调用 lifecycle_reviewer。
subagent_lifecycle_agent = create_deep_agent(
    # model：父 Agent 用它决定何时调用 task、何时汇总结果。
    model=MODEL,
    # subagents：注册 task 工具可路由的目标；元素中的 name 是路由键。
    subagents=[lifecycle_reviewer],
    # middleware：这里只记录父 Agent 生命周期，子 Agent 有自己的 Middleware。
    middleware=[
        # 父 Agent 使用另一字段记录自己的生命周期。
        LifecycleProbeMiddleware("parent", "parent_lifecycle_events"),
    ],
    # state_schema：声明父图和子图回传时允许合并的自定义 State 字段。
    state_schema=LifecycleState,
    # name：父 Graph 在 Studio 和 Trace 中显示的名称。
    name="subagent-lifecycle-agent",
    # system_prompt：要求父模型委派而不是自己执行库存检查。
    system_prompt=(
        "Delegate exactly once to lifecycle-reviewer, then return its conclusion. "
        "Do not perform the inventory review yourself."
    ),
)


# 常规声明式风险子 Agent：独立检查库存和供应商，不接触金额与预算工具。
risk_subagent: SubAgent = {
    # 父模型调用 task 时通过 name 精确选择该子 Agent。
    "name": "risk-reviewer",
    # 父模型会读取 description，判断当前请求是否属于风险检查。
    "description": "Independently checks supplier, inventory, and delivery risks.",
    # 子 Agent 的推理模型；配置在这里不会影响父 Agent。
    "model": MODEL,
    # 子 Agent 仅能看到这两个工具，不会继承父 Agent 的金额/预算工具。
    "tools": [check_inventory, check_supplier],
    # 子 Agent 自己收到的系统提示，限定输出范围和语言。
    "system_prompt": (
        "You are an independent risk reviewer. Use tools, list evidence, and return "
        "only risks and mitigations in Chinese."
    ),
}

# 父 Agent 自己核算金额/预算，再把风险检查委派出去，最后合并两部分结论。
subagent_agent = create_deep_agent(
    # 父 Agent 的模型负责拆分任务并合并最终结论。
    model=MODEL,
    # 父 Agent 可直接调用的工具；不会自动授权给子 Agent。
    tools=[calculate_total, check_budget],
    # 注册后框架会给父模型提供 task 工具用于委派。
    subagents=[risk_subagent],
    # Graph/Studio/Trace 中的父 Agent 名称。
    name="subagent-agent",
    # 父 Agent 的职责说明；子 Agent 使用上面自己的 system_prompt。
    system_prompt=(
        "You lead a procurement review. Check amount and budget yourself, delegate an "
        "independent risk review to risk-reviewer, then merge both conclusions."
    ),
)


# 先用 LangChain create_agent 创建一张可独立运行的财务审核图。
finance_graph = create_agent(
    # 预编译子图内部使用的模型，与稍后的父 Agent 相互独立。
    model=MODEL,
    # 只把财务核算所需工具绑定到这张子图。
    tools=[calculate_total, check_budget],
    # 这张可复用 Graph 在 Trace 中的名称。
    name="finance-review-graph",
    # 只约束财务子图如何使用工具并返回结果。
    system_prompt=(
        "You are a reusable finance review graph. Verify the total and budget, then "
        "return a short Chinese finance conclusion."
    ),
)

# CompiledSubAgent 不重新声明 model/tools，而是直接复用已经编译好的 Runnable 图。
finance_compiled_subagent: CompiledSubAgent = {
    # name：父模型调用 task 时使用的目标名，必须在父级 subagents 中唯一。
    "name": "finance-graph-reviewer",
    # description：给父模型看的路由说明，帮助它判断何时委派财务任务。
    "description": "Runs a precompiled LangChain finance review graph.",
    # runnable：真正被执行的已编译 Graph/Runnable；不是模型名，也不是调用结果。
    "runnable": finance_graph,
}

# 编译式子 Agent 示例：父 Agent 负责供应商/库存，财务部分委派给 finance_graph。
compiled_subagent_agent = create_deep_agent(
    # 父 Agent 的模型负责调用自身工具、委派子图和汇总答案。
    model=MODEL,
    # 这些工具只属于父 Agent，用于库存和供应商审查。
    tools=[check_inventory, check_supplier],
    # 把已编译 finance_graph 注册成 task 工具可调用的目标。
    subagents=[finance_compiled_subagent],
    # 父 Graph 在 Studio/Trace 中的名称。
    name="compiled-subagent-agent",
    # 父提示词规定任务边界，财务子图仍使用它自己的提示词。
    system_prompt=(
        "Check inventory and supplier risk, delegate finance verification to "
        "finance-graph-reviewer, and return one Chinese report."
    ),
)


# 这张图既能在 Studio 中独立运行，也是异步子 Agent 示例调用的远程目标。
remote_research_agent = create_deep_agent(
    # 远程 Graph 运行时自行使用的模型，不会继承调用方父 Agent 的模型。
    model=MODEL,
    # 远程 Graph 自己可用的工具集合。
    tools=[check_inventory, check_supplier],
    # Agent Server 注册和 Trace 中显示的 Graph 名称。
    name="remote-research-agent",
    # 远程研究任务自己的行为约束。
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
        # name：父模型启动/查询后台任务时使用的子 Agent 路由名。
        "name": "remote-procurement-researcher",
        # description：给父模型看的能力说明，影响它何时调用 start_async_task。
        "description": "Runs a long procurement investigation in the background.",
        # graph_id：Agent Server 中注册的 Graph ID，必须与 langgraph.json 一致。
        "graph_id": "remote_research_agent",
        # url：实现 Agent Protocol 的服务根地址，不是 Studio 页面地址。
        "url": server_url,
    }
    # 没有配置 Token 时不发送 Authorization 头，适配本地无鉴权服务。
    if token := os.getenv("AGENT_SERVER_TOKEN"):
        # headers：随每个 Agent Protocol 请求发送，通常用于远程服务鉴权。
        spec["headers"] = {"Authorization": f"Bearer {token}"}
    return spec


# 异步委派示例：start_async_task 立即返回 task_id，不在当前 run 内等待远程结果。
async_subagent_agent = create_deep_agent(
    # 父模型只负责本地推理和调度，不会被复制到远程 Graph。
    model=MODEL,
    # 父 Agent 自己可以直接使用的本地工具。
    tools=[calculate_total, check_budget],
    # AsyncSubAgent 配置会安装 start/check/update/cancel 等后台任务工具。
    subagents=[_remote_researcher()],
    # 父 Graph 在 Studio 和 LangSmith Trace 中的名称。
    name="async-subagent-agent",
    # 提示父模型启动任务后立即返回，避免在同一轮里反复查询。
    system_prompt=(
        "For requests that explicitly ask for background research, call "
        "start_async_task once and return its task_id immediately. Do not poll unless "
        "the user asks for status or results."
    ),
)


# StateBackend 文件示例：Agent 可把分析过程和报告写入 Graph State 的 files 字段。
# 这些 /work、/reports 路径都是虚拟路径，不会直接写入本机磁盘。
backend_agent = create_deep_agent(
    # model：决定何时读写虚拟文件、何时调用业务工具。
    model=MODEL,
    # tools：Agent 可调用的采购证据工具。
    tools=PROCUREMENT_TOOLS,
    # backend：把文件操作映射到当前 Graph State 的 files 字段，不写本机磁盘。
    backend=StateBackend(),
    # Graph/Studio/Trace 中使用的名称。
    name="state-backend-agent",
    # 指定模型应生成哪些虚拟文件以及最终如何告知用户。
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
        # operations：这条规则匹配哪些文件操作；这里仅匹配写入。
        operations=["write"],
        # paths：使用虚拟文件系统 glob 匹配目标路径及其子路径。
        paths=["/reports/drafts/**"],
        # mode=allow：匹配后直接执行，不进入人工审核。
        mode="allow",
    ),
    # 最终报告目录的写入会产生 interrupt，等待调用方给出批准/拒绝决定。
    FilesystemPermission(
        # 对最终报告仍只匹配 write 操作。
        operations=["write"],
        # 只有最终报告目录命中此规则。
        paths=["/reports/final/**"],
        # mode=interrupt：执行前暂停 Graph，等待人工决定。
        mode="interrupt",
    ),
    # 兜底拒绝所有其他路径，防止 Agent 写出约定目录。
    FilesystemPermission(
        # 兜底规则仍针对写入操作。
        operations=["write"],
        # /** 匹配所有未被前面更具体规则处理的虚拟路径。
        paths=["/**"],
        # mode=deny：直接拒绝操作，不进入人工审批。
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
        # 父 Agent 的推理模型。
        model=MODEL,
        # 除只读采购工具外，额外开放有副作用的 publish_review。
        tools=[*PROCUREMENT_TOOLS, publish_review],
        # 文件操作保存在 State 中，便于权限中断后随 Checkpoint 恢复。
        backend=StateBackend(),
        # 控制虚拟文件写操作是允许、拒绝还是中断等待人工确认。
        permissions=HITL_PERMISSIONS,
        # publish_review 属于有外部效果的动作，每次调用都必须人工批准。
        interrupt_on={"publish_review": True},
        middleware=[
            # 限制模型和工具循环次数，配置错误时尽快失败而不是无限运行。
            # run_limit：整次 Graph 运行最多调用 12 次模型；超限直接抛错。
            ModelCallLimitMiddleware(run_limit=12, exit_behavior="error"),
            # run_limit：整次运行最多执行 20 次工具；超限同样抛错。
            ToolCallLimitMiddleware(run_limit=20, exit_behavior="error"),
        ],
        # checkpointer：保存中断现场；恢复时还必须复用相同 thread_id。
        checkpointer=checkpointer,
        # Graph/Studio/Trace 中的稳定名称。
        name="hitl-harness-agent",
        # 模型层面的工作步骤；真正的强制审批由 permissions/interrupt_on 保证。
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
    """创建以项目 workspace 为工作目录、所有变更和命令均需审批的本地 Agent。

    ``virtual_mode`` 只限制内置文件工具的路径，不是操作系统级 shell 沙箱；
    因此本例还会中断所有 ``execute`` 调用，把最终执行权交给人工审核。
    """
    backend = LocalShellBackend(
        # root_dir：内置文件操作的虚拟根目录，也是 shell 命令的默认工作目录。
        root_dir=Path(WORKSPACE_DIR),
        # virtual_mode=True：/artifacts 等文件工具路径会映射到 root_dir 并阻止 ..；
        # 它不限制 execute 中的任意 shell 路径，所以命令仍必须人工审批。
        virtual_mode=True,
        # 限制单条命令运行时间及回传输出大小，避免失控进程和超大上下文。
        timeout=30,
        # max_output_bytes：单次命令最多回传给模型的 stdout/stderr 字节数。
        max_output_bytes=20_000,
        # 不继承完整父进程环境，防止密钥等无关变量进入 shell。
        env=_safe_local_env(),
        # inherit_env=False：不自动继承父进程中的 API Key 等环境变量。
        inherit_env=False,
    )
    return create_deep_agent(
        # 模型负责生成文件操作或命令调用请求。
        model=MODEL,
        # 可执行 Backend 把文件和 shell 工具映射到受限本地 workspace。
        backend=backend,
        # deepagents 0.7.x 不允许可执行 Backend 配合 FilesystemPermission：shell
        # 命令可能绕过路径规则，所以这里让所有文件变更和命令统一进入 HITL 审批。
        interrupt_on={
            # True 表示每次调用都在实际操作前暂停，等待 approve/edit/reject。
            "write_file": True,
            "edit_file": True,
            "delete": True,
            "execute": True,
        },
        # 保存待审批调用及 Graph 状态，恢复时必须配合同一个 thread_id。
        checkpointer=checkpointer,
        # Graph/Studio/Trace 中显示的名称。
        name="local-shell-agent",
        # 给模型的工作约束；真正执行 shell 前仍由 interrupt_on 交给人工决定。
        system_prompt=(
            "This is a local development demonstration. Work only inside the current "
            "workspace, write files only below /artifacts, never use the network, and "
            "request approval before execute."
        ),
)


# Studio 使用的模块级 Graph；CLI 需要恢复审批时会调用 builder 创建带 saver 的实例。
local_shell_agent = build_local_shell_agent()

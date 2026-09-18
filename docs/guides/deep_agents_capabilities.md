# Deep Agents 进阶能力：子 Agent、Backend、Skills 与 Sandbox

这部分内容从[入门教程](../notes/python_deep_agents_notes.md)中独立出来。建议先完成单工具、多工具编排、报告生成和程序化验收，再按需学习本专题。

## 1. 声明式 SubAgent：按职责分工

子 Agent 适合任务真的变复杂的时候。

比如同一笔采购评审，可以分成：

- 采购研究员：看库存、交期、供应商。
- 财务复核员：看预算、审批路径。
- 合规审查员：看合规风险。

这节可以运行，但如果你刚开始学 Deep Agents，可以先跳过。


```python
subagents = [
    {
        "name": "procurement-researcher",
        "description": "负责查询库存、交期、替代方案和供应商风险。",
        "system_prompt": "你是采购研究员。只关注库存、交期、替代方案和供应商风险。",
        "tools": [check_inventory, check_supplier],
    },
    {
        "name": "finance-reviewer",
        "description": "负责检查预算是否足够，并生成审批路径。",
        "system_prompt": "你是财务复核员。只关注预算是否足够、审批路径是否完整。",
        "tools": [check_budget, build_approval_route],
    },
    {
        "name": "compliance-reviewer",
        "description": "负责检查采购申请的合规风险。",
        "system_prompt": "你是合规审查员。只关注合规问题和整改建议。",
        "tools": [compliance_check],
    },
]

subagent_review_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    subagents=subagents,
    system_prompt=(
        "你是采购评审主控 Agent。"
        "优先调用 run_procurement_review 获得完整事实。"
        "必要时可以把采购、财务、合规问题交给子 Agent 复核。"
        "最终输出 Markdown 报告，包含申请摘要、关键风险、审批路径和最终建议。"
    ),
)

subagent_result = subagent_review_agent.invoke({"messages": [{"role": "user", "content": request_text}]})
print(subagent_result["messages"][-1].content)
```

声明式 SubAgent 的 isolated/fork、State 传播、权限继承、生命周期、LangSmith 观察点和无 Key 测试见：[声明式 SubAgent 独立专题](../../deep_agent_examples/examples/declarative_subagent/README.md)。


## 2. `CompiledSubAgent`：复用已经构建好的 Agent 或 LangGraph

上一节传入的是声明式 `SubAgent`：提供 `system_prompt`、`tools` 等配置，由 Deep Agents 帮我们创建子 Agent。

如果子 Agent 已经通过 LangChain 的 `create_agent()` 或 LangGraph 构建完成，就应该使用 `CompiledSubAgent`，把现成的 `runnable` 直接交给主 Agent。这里的正确名称是 **CompiledSubAgent**，不是 Complicate Subagent。

| 对比项 | 声明式 `SubAgent` | `CompiledSubAgent` |
| --- | --- | --- |
| 传入内容 | 模型、提示词、工具等配置 | 已构建好的 `runnable` |
| 谁负责构建 | Deep Agents | 业务代码自己构建 |
| 适用场景 | 简单的专业分工 | 复用已有 Agent、自定义 StateGraph 或复杂中间件 |

下面把一个已经构建好的财务复核 Agent 注册为 `CompiledSubAgent`：

```python
from langchain.agents import create_agent
from deepagents import CompiledSubAgent

finance_review_graph = create_agent(
    model=llm,
    tools=[check_budget, check_supplier, build_approval_route],
    system_prompt=(
        "你是财务复核员。先查询预算和供应商风险，再生成审批路径。"
        "只返回预算结论、资金风险和审批路径。"
    ),
)

finance_compiled_subagent: CompiledSubAgent = {
    "name": "finance-graph-reviewer",
    "description": "使用已经构建好的财务复核图，独立检查预算、资金风险和审批路径。",
    "runnable": finance_review_graph,
}

compiled_subagent_review_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    subagents=[finance_compiled_subagent],
    system_prompt=(
        "你是采购评审主控 Agent。先调用 run_procurement_review 获取完整事实，"
        "再把财务复核任务委派给 finance-graph-reviewer，最后合并两份结论。"
    ),
)

compiled_subagent_result = compiled_subagent_review_agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": f"请评审以下采购申请，并让财务子 Agent 独立复核：{request_text}",
            }
        ]
    }
)
print(compiled_subagent_result["messages"][-1].content)
```

使用时注意：

- `runnable` 的返回状态必须包含 `messages`，否则主 Agent 无法取得子 Agent 的结果。
- `CompiledSubAgent` 不会继承主 Agent 的 `model`、`tools`、`middleware`、`state_schema` 或 `interrupt_on`；这些能力要在构建 `runnable` 时配置。
- 默认情况下，子 Agent 只看到主 Agent 通过 `task` 工具交给它的任务描述，不会自动获得完整对话。
- 如果返回状态包含非空的 `structured_response`，Deep Agents 会把它序列化后交给主 Agent；否则使用最后一条非空 `AIMessage`。

因此，只有在确实需要复用现成图或自定义状态时才使用 `CompiledSubAgent`；普通角色分工继续使用上一节的声明式写法即可。

可直接运行的真实示例、确定性测试、State schema、输出契约、HITL 和 checkpointer 边界见：[CompiledSubAgent 独立专题](../../deep_agent_examples/examples/compiled_subagent/README.md)。


## 3. `AsyncSubAgent`：把长任务放到远程后台执行

`AsyncSubAgent` 不是“在本进程里并发调用一个子 Agent”，而是通过 LangGraph SDK 在远程 **Agent Protocol** 服务上启动后台任务。主 Agent 会立即拿到 `task_id`，可以继续处理当前对话，之后再查询、追加指令或取消任务。

它适合耗时较长、可以独立运行的研究、批量分析和报告生成任务；几秒钟能完成的调用继续使用同步 `SubAgent` 即可。

```python
from deepagents import AsyncSubAgent, create_deep_agent

remote_researcher: AsyncSubAgent = {
    "name": "remote-procurement-researcher",
    "description": "在后台调查供应商、市场价格和交付风险。",
    "graph_id": "procurement_research_agent",
    "url": "https://your-agent-protocol.example.com",
    # 自托管服务需要认证时再传 headers；不要把密钥写死在代码里。
    # "headers": {"Authorization": f"Bearer {token}"},
}

async_review_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    subagents=[remote_researcher],
    system_prompt=(
        "采购研究预计耗时较长时，使用 remote-procurement-researcher 启动后台任务。"
        "不要持续轮询；只有用户要求查看进度或结果时才检查任务。"
    ),
)

async_result = await async_review_agent.ainvoke(
    {"messages": [{"role": "user", "content": "后台调查供应商风险，并先继续处理采购申请。"}]}
)
print(async_result["messages"][-1].content)
```

配置字段只有几个：

| 字段 | 是否必填 | 作用 |
| --- | --- | --- |
| `name` | 是 | 主 Agent 选择子 Agent 时使用的唯一名称 |
| `description` | 是 | 说明何时应该委派 |
| `graph_id` | 是 | 远程服务中的 graph 名称或 assistant ID |
| `url` | 否 | Agent Protocol 服务地址；省略时使用本地 ASGI transport |
| `headers` | 否 | 自托管服务的认证请求头 |

注册后，Deep Agents 会提供 `start_async_task`、`check_async_task`、`update_async_task`、`cancel_async_task` 和 `list_async_tasks` 工具。任务元数据保存在 state 的 `async_tasks` 中，但真正的执行和线程数据在远程服务端。

注意以下边界：

- 省略 `url` 的本地 ASGI transport 只能从 `ainvoke` 等异步入口使用；同步 `invoke` 必须连接一个可访问的 URL。
- `AsyncSubAgent` 不继承主 Agent 的本地 middleware、skills、state schema 或 HITL 配置；这些能力要配置在远程 graph 内。
- LangGraph Platform / LangSmith Deployment 的认证通常读取环境变量；自托管服务使用 `headers`。
- 不要让模型高频轮询任务。启动后继续做其他工作，只在用户需要结果时检查。

远程 thread/run 状态机、五个管理工具、父远程两侧 LangSmith 关联方式，以及无服务器 Fake Agent Protocol 测试见：[AsyncSubAgent 独立专题](../../deep_agent_examples/examples/async_subagent/README.md)。


## 4. Backends 工具箱：文件存在哪里，命令在哪里执行

Backend 是 Deep Agents 文件工具的存储和执行边界。`ls`、`read_file`、`write_file`、`edit_file`、`glob`、`grep` 都通过 backend 工作；只有实现 `SandboxBackendProtocol` 的 backend 才能真正使用 `execute`。

| Backend | 数据位置与生命周期 | `execute` | 适用场景 |
| --- | --- | --- | --- |
| `StateBackend` | LangGraph state；同一 thread 内有效 | 否 | 默认选择、临时报告、基于 State 的 Skills |
| `StoreBackend` | LangGraph `BaseStore`；可跨 thread 持久化 | 否 | 用户记忆、团队资料、长期 Skills |
| `FilesystemBackend` | 当前主机文件系统 | 否 | 可信的本地开发和 CI 文件操作 |
| `LocalShellBackend` | 当前主机文件系统和本机 shell | 是 | 可信的个人开发环境；**不提供隔离** |
| `CompositeBackend` | 按路径前缀路由到多个 backend | 取决于默认 backend | 临时文件与持久资料混合存储 |
| `ContextHubBackend` | LangSmith Hub agent repo | 否 | 共享、版本化的 Agent 上下文 |
| `LangSmithSandbox` | LangSmith 云沙箱 | 是 | 需要隔离执行的云端任务 |

`StateBackend` 在一次 graph 运行中总是可用；要让文件跨多次调用留在同一 thread，必须配置 checkpointer，并在调用时复用同一个 `thread_id`。

最小用法是显式传入默认的 `StateBackend`：

```python
from deepagents.backends import StateBackend

state_backend_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    backend=StateBackend(),
    system_prompt="把中间结果写到 /work/，最终再汇总。",
)
```

要把临时文件留在 state，同时把长期资料写入 Store，可以按虚拟路径路由：

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
composite_backend = CompositeBackend(
    default=StateBackend(),
    routes={
        "/memory/": StoreBackend(
            store=store,
            namespace=lambda runtime: ("procurement-assistant", "filesystem"),
        )
    },
)

backend_agent = create_deep_agent(
    model=llm,
    backend=composite_backend,
)
```

这里的 `InMemoryStore` 只用于学习，进程退出后数据仍会丢失。生产环境应替换成实际持久化的 `BaseStore`，并使用用户或租户标识构造 namespace，避免不同用户互相看到文件。

选择顺序可以保持简单：

1. 只是当前任务的中间文件：`StateBackend`。
2. 需要跨会话保存：`StoreBackend`。
3. 可信本地开发需要直接操作文件：`FilesystemBackend`。
4. 需要执行不可信代码：真正隔离的 sandbox backend。
5. 不同目录需要不同生命周期：`CompositeBackend`。


## 5. 基于 State 的动态 Skills

`skills=[...]` 配置的是**要扫描的 backend 目录路径**，不是 Skill 工具列表。固定目录 Skill 和基于 State 的 Skill 都使用 progressive disclosure：`SkillsMiddleware` 先扫描每个 `SKILL.md` 的 frontmatter，把名称、描述和路径放进系统提示词；模型判断匹配后，再通过 `read_file` 读取完整正文。

因此，“静态 Skill 把全部正文塞入 prompt，动态 Skill 才按需加载”并不符合当前实现。两者的差别是 Skill 文件来自哪里，而不是正文加载策略：

| 维度 | 固定目录 Skill | 基于 `StateBackend` 的动态 Skill |
| --- | --- | --- |
| source 配置 | Graph 构建时配置路径 | Graph 构建时同样配置路径 |
| 文件来源 | 文件系统、Store 或其他 backend | 当前 thread 的 `state["files"]` |
| 进入 prompt 的内容 | metadata 索引 | metadata 索引 |
| 完整正文 | 模型需要时调用 `read_file` | 模型需要时调用 `read_file` |
| 动态点 | 部署方维护 backend 内容 | 调用方为每个新 thread 注入不同文件集合 |

真实执行链路是：

```text
invoke(files=...)
  -> StateBackend 暴露 files channel
  -> SkillsMiddleware.before_agent 扫描 source
  -> 解析 frontmatter 并写入私有 skills_metadata
  -> wrap_model_call 把 metadata 索引追加到 system prompt
  -> 模型匹配 Skill
  -> read_file 读取完整 SKILL.md
  -> 模型按正文调用业务工具
```

Middleware 扫描阶段为了提取 frontmatter 会从 backend 读取文件，但这不等于完整正文已经进入模型上下文。正文只有在 `read_file` 的工具结果进入消息后才消耗相应的模型上下文。

使用 `StateBackend` 时，可以在每次新会话开始时把不同的 Skill 文件放进输入 state，从而根据用户、租户或任务动态提供技能：

```python
from deepagents.backends import StateBackend

PROCUREMENT_SKILL = """---
name: procurement-review
description: Review enterprise purchase requests for budget, supplier and compliance risks
---

# Procurement Review

1. Parse the request into structured fields.
2. Check inventory, supplier, budget and compliance evidence.
3. Separate blocking risks from recommendations.
4. Never submit an approval without explicit user confirmation.
"""

dynamic_skill_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    backend=StateBackend(),
    skills=["/skills/session/"],
)

dynamic_skill_result = dynamic_skill_agent.invoke(
    {
        "messages": [{"role": "user", "content": request_text}],
        "files": {
            "/skills/session/procurement-review/SKILL.md": {
                "content": PROCUREMENT_SKILL,
                "encoding": "utf-8",
            }
        },
    }
)
```

动态点在于 `files` 的内容由应用在调用前决定，而不是让模型任意加载所有 Skills。例如可以先根据 `tenant_id` 和用户角色在服务层选择允许的 Skill，再组装输入 state。身份和角色必须来自认证后的 Context 或服务端会话，不能相信用户文本或模型生成的 State 字段。

这里实际有两次选择：

1. 服务端用确定性策略计算“角色允许集合 ∩ 当前任务需要集合”，只把结果注入 State。这一层负责授权和租户隔离。
2. 模型在已经允许暴露的 metadata 中判断哪个 Skill 与当前任务匹配。这一层只是语义路由，不是授权。

Skill 也不会自动增加或移除工具。frontmatter 中的实验性 `allowed-tools` 当前只显示在 Skill 索引里，不是强制 ACL。文件权限、高风险审批和代码隔离仍应分别由 `FilesystemPermission`、`interrupt_on` 和真正的 Sandbox backend 实施。

需要区分三个概念：

| 需求 | 推荐实现 |
| --- | --- |
| 每个新会话使用不同 Skill 集合 | `StateBackend` + 调用时传入不同 `files` |
| 同一用户跨会话复用 Skill | `StoreBackend`，按用户 namespace 隔离 |
| 每一轮都重新计算 Skill 来源 | 自定义 middleware，或为该轮构建新的 Agent；内置 `SkillsMiddleware` 不会自动重载 |

`SkillsMiddleware` 会把解析后的元数据缓存在 `state["skills_metadata"]`，同一 checkpointed session 后续轮次如果已经存在该字段，就跳过重新扫描。因此在同一 thread 中修改 `files` 并不会自动刷新技能目录。最稳妥的做法是：Skill 集合变化时开启新 thread；只有确实需要逐轮热切换时才编写自定义 middleware。

这会带来几个容易忽略的结果：新增 Skill 后模型无法发现它；修改 `name` 或 `description` 后仍使用旧索引；删除 Skill 后旧路径仍可能出现在索引中，但 `read_file` 会失败。一个 thread 的能力集合应保持稳定，并在 trace metadata 中记录 Skill bundle 版本。

多个 `skills` source 会按顺序加载，同名 Skill 由后面的 source 覆盖前面的 source，适合实现“内置默认 -> 用户 -> 项目”的分层覆盖。所有 backend 路径都使用 POSIX 风格 `/`。

可启动示例、State 字段表、可信路由代码、LangSmith 观察点和排错表见：[基于 State 的动态 Skills：机制、路由与安全边界](../../deep_agent_examples/examples/dynamic_skills/README.md)。

仓库中的代码不是伪代码，可以直接运行：

```powershell
cd deep_agent_examples

# 真实模型；配置 LANGSMITH_TRACING=true 后上传 trace
uv run python examples/dynamic_skills/run.py

# Fake Model 确定性测试；不需要模型或 LangSmith Key
uv run python examples/dynamic_skills/test.py
```


## 6. 云沙箱、OpenSandbox 与本地执行

“能执行 shell”不等于“有沙箱”。Deep Agents 只要求执行型 backend 实现 `SandboxBackendProtocol`，真正的容器、虚拟机、网络策略、资源限额和销毁机制由 backend 提供者负责。

| 方案 | 隔离位置 | 优点 | 主要边界 |
| --- | --- | --- | --- |
| 云沙箱 | 托管容器或 VM | 隔离、弹性、生命周期 API 完整 | 成本、网络延迟、数据合规 |
| OpenSandbox | 自己的 Docker / Kubernetes | 数据和基础设施可控，无按秒平台绑定 | 要自己运维服务和镜像 |
| `LocalShellBackend` | **没有隔离，直接在主机执行** | 启动最简单、适合个人开发 | 可读取密钥、改写文件、耗尽主机资源 |
| 自定义本地 sandbox | 本机 Docker / VM | 本地可控且有进程隔离 | 需要自己实现或维护 backend 适配 |

Deep Agents 当前直接包含 `LangSmithSandbox`；Daytona、E2B、Modal、Runloop 等通过独立集成包提供。无论选择哪家，只要 backend 实现 `SandboxBackendProtocol`，传给 `create_deep_agent(backend=...)` 后都能获得文件工具和 `execute`。

本地可信开发可以这样使用 `LocalShellBackend`：

```python
from pathlib import Path
from deepagents.backends import LocalShellBackend
from langgraph.checkpoint.memory import MemorySaver

local_backend = LocalShellBackend(
    root_dir=Path.cwd(),
    inherit_env=False,
    env={"PATH": "C:\\Windows\\System32"},
    timeout=60,
)

local_agent = create_deep_agent(
    model=llm,
    backend=local_backend,
    interrupt_on={"execute": True},
    checkpointer=MemorySaver(),
)
```

上面仍然不是安全沙箱。`virtual_mode=True` 只约束文件工具的虚拟路径，shell 命令依然能使用当前用户权限访问主机。不要把 `LocalShellBackend` 放在 Web API、多租户系统或不可信输入前面。

OpenSandbox 是可自托管的隔离运行时，社区适配包的典型结构如下：

```python
# 架构示例：使用前必须先核对版本兼容性。
from opensandbox.sync.sandbox import SandboxSync
from langchain_opensandbox import OpenSandboxSandbox

sandbox = SandboxSync.create("python:3.11-slim")
try:
    sandbox_agent = create_deep_agent(
        model=llm,
        backend=OpenSandboxSandbox(sandbox=sandbox),
    )
    sandbox_result = sandbox_agent.invoke(
        {"messages": [{"role": "user", "content": "创建并运行一个只打印 hello 的 Python 脚本。"}]}
    )
finally:
    sandbox.kill()
```

**当前项目不要直接安装这段示例的适配包。** 截至本文核对时，`langchain-opensandbox 0.1.0` 声明依赖 `deepagents >=0.6.12,<0.7`，而本项目使用 `deepagents 0.7.x`。应等待兼容版本、在独立环境锁定旧版，或基于当前 `BaseSandbox` / `SandboxBackendProtocol` 自行适配；不要为了示例降级主项目依赖。

生产 sandbox 至少要处理：每个 thread/tenant 的实例隔离、CPU/内存/磁盘限制、网络出口策略、密钥注入、命令超时、文件上传下载、审计日志、异常销毁和闲置回收。HITL 可以减少误操作，但不能代替隔离层。


## 7. Harness Engineering：设计 Agent 的运行环境

完整专题见：[Harness Engineering：从模型能力到可靠 Agent 系统](./harness_engineering.md)。下面保留与 Deep Agents 直接相关的摘要。

Prompt Engineering 关注“给模型什么指令”；Harness Engineering 关注“模型在什么系统里运行”。Harness 是包围模型的工程外壳，决定上下文如何进入、工具如何暴露、状态如何持久化、危险操作如何拦截，以及结果如何评测。

```text
用户请求
  -> 上下文与记忆
  -> 模型 + Prompt
  -> 工具 / Skills / Subagents
  -> Backend / Sandbox
  -> Checkpoint / HITL / Trace / Evaluation
  -> 可验证结果
```

在 Deep Agents 中可以这样映射：

| Harness 关注点 | Deep Agents 能力 |
| --- | --- |
| 长任务规划与上下文控制 | planning、summarization、filesystem |
| 专业知识按需加载 | Skills、memory |
| 任务分工 | `SubAgent`、`CompiledSubAgent`、`AsyncSubAgent` |
| 状态和恢复 | LangGraph state、checkpointer、store |
| 权限和人工确认 | `permissions`、`interrupt_on`、HITL middleware |
| 隔离执行 | `SandboxBackendProtocol` 及具体 sandbox backend |
| 可观测与质量 | stream、trace、结构化输出、轨迹评测 |

`HarnessProfile` 是 Deep Agents 中针对**模型差异**调整 harness 的 API，不等于 Harness Engineering 的全部。它可以调整 prompt 组装、工具描述、工具可见性、middleware 和默认 general-purpose subagent：

```python
from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)

register_harness_profile(
    "openai:gpt-5.4",
    HarnessProfile(
        system_prompt_suffix="输出前检查证据来源和未解决风险。",
        excluded_tools=frozenset({"execute"}),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)
```

这套 Profile API 仍是 beta。`excluded_tools` 只影响模型能看到什么，不是安全边界；真正的安全仍要依赖最小权限工具、`permissions`、HITL 和隔离 backend。Profile 的 `extra_middleware` 也不会注入已经编译好的 `CompiledSubAgent` 或远程 `AsyncSubAgent`。

生产 Harness 的最小检查清单：

- 先用确定性代码固定不可违反的业务规则，再让模型处理开放判断。
- 工具只暴露完成任务所需的最小权限；读写和执行权限分开。
- 写操作、付款、审批提交等高风险动作必须有幂等键、审计和人工确认。
- 控制上下文预算：长期记忆、当前 state、检索结果和 Skills 分层加载。
- 每个外部调用都有超时、重试上限和明确失败路径。
- 保存模型调用、工具参数、状态变化和最终证据，敏感字段先脱敏。
- 同时评测最终答案和执行轨迹，包括拒绝路径、超时、恢复和权限绕过。

一个好的 Harness 不追求让 Agent “更自由”，而是让它在可观察、可恢复、权限明确的边界内完成更多任务。

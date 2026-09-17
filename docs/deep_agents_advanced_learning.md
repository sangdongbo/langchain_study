# Deep Agents 进阶学习路线：从会调用工具到可上线

这份文档回答两个问题：

1. 学完基础工具、子 Agent、Backend、Skills 和 Sandbox 后，还缺什么？
2. 怎样把零散功能组合成一个可恢复、可审计、可评测的 Agent 系统？

本文不再扩展采购案例的业务规则，而是补齐 Deep Agents 的工程主线。示例按仓库中可正常导入的 `deepagents 0.7.13` 与 `langchain 1.3.18` 整理；这些 API 仍在快速变化，升级依赖后应重新核对签名和行为。

> 环境提醒：当前仓库根目录 `.venv` 中的 `deepagents 0.6.12` 与 `langchain 1.3.1` 已出现导入不兼容。学习和运行示例时要确认 Notebook Kernel、终端解释器和安装依赖使用的是同一个环境，不能只看 `pip install` 是否成功。

## 1. 当前覆盖与学习缺口

已有主教程已经覆盖：

- 普通函数、单工具和多工具编排。
- `SubAgent`、`CompiledSubAgent`、`AsyncSubAgent`。
- `StateBackend`、`FilesystemBackend`、`StoreBackend`、`CompositeBackend`。
- Memory、静态 Skills、基于 State 的动态 Skills。
- 本地执行、云沙箱、OpenSandbox 的角色与边界。
- Harness Engineering、报告文件和程序化结果验收。

下一阶段不应只是继续增加工具数量，而要补齐下面这些能力：

| 主题 | 要解决的问题 | 学完后的产物 |
| --- | --- | --- |
| 版本与环境 | 为什么同一段代码在不同 Kernel 中表现不同？ | 可复现的依赖锁定和启动检查 |
| State / Context | 哪些数据会变，哪些身份信息必须可信且不可由模型改写？ | 自定义状态和运行时上下文 |
| Checkpointer / Store | 怎样恢复同一会话，怎样跨会话保留资料？ | 线程恢复与租户隔离存储 |
| Permissions / HITL | 怎样限制文件读写并让高风险动作等待审批？ | 最小权限规则和审批恢复流程 |
| Memory / Skills / RAG | 偏好、能力说明、外部证据分别放在哪里？ | 分层知识设计 |
| Structured Output | 怎样让结果进入后续程序，而不靠解析自然语言？ | 可校验的业务结果对象 |
| Context Management | 长任务如何避免上下文持续膨胀？ | 摘要、卸载和缓存策略 |
| MCP / 多模态 / Sandbox | 外部工具、文件和代码执行如何治理？ | 工具目录与执行信任边界 |
| Trace / Eval / Rubric | 怎样判断 Agent 真正完成了任务？ | 离线数据集、轨迹检查和质量门槛 |
| 生产运行 | 怎样支持多租户、恢复、限流、审计和故障处理？ | 上线检查清单 |

## 2. 推荐学习顺序

### 第一阶段：必须掌握

按下面顺序学习，先建立正确的数据和安全边界：

1. 版本、模型能力和运行环境检查。
2. `State`、`Context`、`Checkpointer`、`Store`。
3. 文件权限、普通工具审批和 Human-in-the-loop。
4. Memory、Skills、RAG 的分工。
5. Structured Output 和应用层校验。

完成标准：同一个 `thread_id` 能恢复任务；不同用户不能读到对方数据；高风险写操作会暂停；结果能被 Pydantic 模型校验。

### 第二阶段：复杂长任务

1. Summarization、context offloading、prompt caching。
2. Middleware 的调用顺序和状态字段。
3. Streaming、trace、错误分类与重试。
4. MCP 工具治理、多模态读取和沙箱执行。
5. SubAgent 的上下文隔离和失败传播。

完成标准：任务运行时间变长后仍可观测、可中断、可恢复，工具大输出不会一直占据模型上下文。

### 第三阶段：生产与评测

1. 确定性检查、模型评分和人工抽检。
2. Rubric 驱动的修改循环。
3. 多租户身份、秘密管理和权限审计。
4. 持久化基础设施、队列、并发、幂等和灾难恢复。
5. 成本、延迟、成功率和安全事件监控。

完成标准：不仅能演示一次，还能解释失败发生在哪一层、怎样恢复、谁批准过、结果为何可信。

## 3. 四种数据边界：State、Context、Checkpointer、Store

这四个概念最容易混淆，可以先记住：

```text
State        = 本次任务正在变化的数据
Context      = 本次运行可信且不应被模型改写的身份与配置
Checkpointer = 按 thread_id 保存和恢复 State
Store        = 跨 thread 保存长期数据
```

| 概念 | 生命周期 | 是否可变 | 典型内容 | 不应该放什么 |
| --- | --- | --- | --- | --- |
| State | 一个线程的执行过程 | 是 | messages、todos、中间结果、临时文件 | API Key、可信租户身份 |
| Context | 一次调用或运行 | 业务上视为不可变 | user_id、tenant_id、权限、请求来源 | 模型生成的中间结论 |
| Checkpointer | 同一 `thread_id` 的多次调用 | 保存 State 快照 | 中断点、会话消息、待审批操作 | 跨用户共享的长期知识 |
| Store | 跨线程、跨会话 | 是 | 用户偏好、项目记忆、持久文件 | 没有命名空间的多租户数据 |

自定义 `state_schema` 必须继承 `DeepAgentState`，否则可能丢失框架为 `messages` 配置的 `DeltaChannel` reducer：

```python
from dataclasses import dataclass
from typing import NotRequired

from deepagents import create_deep_agent
from deepagents.graph import DeepAgentState
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.store.memory import InMemoryStore


class ProcurementState(DeepAgentState):
    request_id: NotRequired[str]
    risk_score: NotRequired[int]


@dataclass(frozen=True)
class RunContext:
    user_id: str
    tenant_id: str
    role: str


checkpointer = InMemorySaver()  # 只适合学习和本地开发
store = InMemoryStore()         # 只适合学习和本地开发

agent = create_deep_agent(
    model=llm,
    state_schema=ProcurementState,
    context_schema=RunContext,
    checkpointer=checkpointer,
    store=store,
)

config = {"configurable": {"thread_id": "tenant-a:purchase-1001"}}
context = RunContext(user_id="u-17", tenant_id="tenant-a", role="buyer")

result = agent.invoke(
    {
        "messages": [{"role": "user", "content": "检查这份采购申请"}],
        "request_id": "PR-1001",
    },
    config=config,
    context=context,
)
```

关键规则：

- `thread_id` 应由服务端生成或校验，不能直接相信模型或任意客户端输入。
- Context 中的身份和角色应来自鉴权层，而不是用户消息里的“我是管理员”。
- `InMemorySaver` 和 `InMemoryStore` 进程退出后会丢失，只用于学习和测试。
- 生产 Checkpointer 要评估并发、序列化、保留期、加密和故障恢复。
- `StateBackend` 的文件要跨调用保留，需要 Checkpointer 和相同 `thread_id`。
- Store 必须按租户、用户或项目建立 namespace，禁止所有用户共用一个默认空间。

## 4. StateBackend 和 StoreBackend 怎样组合

临时工作文件适合放 State，长期记忆适合放 Store。`CompositeBackend` 可以按路径路由：

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend


def memory_namespace(runtime):
    context = runtime.context
    return ("tenant", context.tenant_id, "user", context.user_id, "filesystem")


backend = CompositeBackend(
    default=StateBackend(),
    routes={
        "/memories/": StoreBackend(
            store=store,
            namespace=memory_namespace,
        ),
    },
)

agent = create_deep_agent(
    model=llm,
    backend=backend,
    context_schema=RunContext,
    checkpointer=checkpointer,
    store=store,
)
```

此时可以约定：

- `/workspace/**`、`/reports/**`：当前线程的工作产物。
- `/memories/**`：跨线程长期保留，但按用户和租户隔离。
- 大型原始文件：放对象存储，State 或 Store 只保存 URI、摘要和校验值。

Store 是持久化能力，不自动等于“记忆策略”。仍需决定谁能写、写什么、多久过期、怎样纠错和删除。

## 5. 文件权限与 Human-in-the-loop

`FilesystemPermission` 只有三个字段：`operations`、`paths`、`mode`。当前版本中：

- `operations` 是 `read` 或 `write`。
- `mode` 是 `allow`、`deny` 或 `interrupt`。
- 第一条匹配规则生效。
- 没有规则匹配时默认允许。

因此，生产规则通常需要在末尾显式兜底：

```python
from deepagents.middleware import FilesystemPermission


permissions = [
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

agent = create_deep_agent(
    model=llm,
    permissions=permissions,
    checkpointer=checkpointer,
)
```

审批流程的工程要点：

1. 调用进入中断后保存 `thread_id` 和中断信息。
2. 前端展示准确的工具名、参数、目标资源和风险说明。
3. 审批人只能批准其权限范围内的操作。
4. 使用同一个 `thread_id` 恢复，而不是重新发起整项任务。
5. 审批记录写入不可抵赖的审计日志。
6. 拒绝、修改参数、超时三种情况都要有明确状态。

必须理解两个限制：

- 权限规则约束的是 `FilesystemMiddleware` 暴露给 Agent 的文件工具；业务代码直接调用 backend 时不会自动经过这些规则。
- 文件权限不等于代码执行沙箱。`execute`、MCP 工具、HTTP API 和自定义写工具要分别做授权、隔离和审计。

## 6. Memory、Skills、RAG 不要混用

| 能力 | 解决什么问题 | 何时进入上下文 | 适合内容 | 更新方式 |
| --- | --- | --- | --- | --- |
| Memory | 让 Agent 记住长期规则和偏好 | 配置的 `AGENTS.md` 会进入系统上下文 | 用户偏好、项目约定、稳定规则 | 受控写入、纠错、过期 |
| Skills | 告诉 Agent 某类任务应该怎样做 | 先看技能索引，需要时再读正文 | SOP、领域步骤、工具用法、模板 | 版本化发布 |
| RAG | 为当前问题找到外部事实证据 | 查询命中后进入当前任务上下文 | 文档段落、政策、产品资料 | 索引同步和召回 |
| State | 保存任务执行现场 | 整个线程内 | 中间结果、待办、工具输出 | 图节点和 middleware |

选择原则：

- 每次都必须遵守的稳定规则放 Memory 或 system prompt。
- 只有处理特定任务才需要的长说明放 Skill。
- 经常变化、数量很大、需要引用来源的知识放 RAG。
- 当前任务的临时推导放 State，不要写成长久记忆。

动态 Skill 的 State 只应该决定“本轮暴露哪些技能”，不要让模型自行伪造身份字段来获得更高权限。技能选择可动态，授权判断必须来自可信 Context。

还要区分“文件来源动态”和“每轮自动换能力”：`StateBackend` 允许应用为每个新 thread 注入不同的 Skill 文件，但内置 `SkillsMiddleware` 会在首次扫描后缓存 `skills_metadata`。固定目录 Skill 与 State Skill 都只把 metadata 索引放进 system prompt，完整正文仍由模型按需 `read_file`；它们都不会自动挂载工具或实施权限。完整执行链路、缓存失效和可运行示例见：[基于 State 的动态 Skills](../deep_agent_examples/DYNAMIC_SKILLS.md)。

## 7. Structured Output 与模型兼容性

自然语言回答适合人看，结构化输出适合程序继续处理：

```python
from typing import Literal

from langchain.agents.structured_output import ToolStrategy
from pydantic import BaseModel, Field


class ReviewDecision(BaseModel):
    decision: Literal["approve", "reject", "manual_review"]
    risk_score: int = Field(ge=0, le=100)
    reasons: list[str]
    required_approvers: list[str]


agent = create_deep_agent(
    model=llm,
    response_format=ToolStrategy(ReviewDecision),
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "评审采购申请 PR-1001"}]}
)
decision = result["structured_response"]
```

不要假设所有 OpenAI-compatible 服务都支持相同的 structured output。仓库现有 Notebook 已遇到过 `This response_format type is unavailable now`，推荐按能力逐级降级：

1. 已验证模型原生支持时，使用 `ProviderStrategy`。
2. 模型支持可靠工具调用时，使用 `ToolStrategy`。
3. 两者都不可用时，定义一个明确的“提交结果”工具，并在应用层做 Pydantic 校验。
4. 校验失败只允许有限次数修复，之后转人工或返回可解释错误。

结构化只保证形状，不保证事实正确。金额、权限、库存和政策判断仍应由确定性代码或可信数据源验证。

## 8. 长上下文管理与 Middleware

Deep Agents 默认组合了文件系统、子 Agent、summarization、工具调用修补等 middleware，并根据模型能力加入 prompt caching。理解默认 Harness 比盲目追加 middleware 更重要。

长任务的四层处理策略：

1. **减少输入**：只提供本步需要的工具、文件片段和检索结果。
2. **结果卸载**：大型工具输出写入文件，消息只保留路径、摘要和关键字段。
3. **历史摘要**：接近上下文窗口时总结早期消息；原始历史可卸载到 `/conversation_history/`。
4. **上下文隔离**：把独立调查交给 SubAgent，只把结论和证据返回主 Agent。

设计自定义 middleware 时要回答：

- 它在模型调用前还是工具调用后工作？
- 它新增哪些 State 字段，字段是否应该是私有状态？
- 它和 summarization、memory、prompt caching 的先后顺序是什么？
- 重试时是否会重复产生外部副作用？
- trace 中哪些字段需要脱敏？

Prompt caching 是成本和延迟优化，不是正确性机制。只有稳定前缀、模型供应商支持且缓存命中时才有效。

## 9. Streaming、Trace 和错误分类

Streaming 不只是逐字显示。复杂 Agent 至少应区分：

- 模型 token 或消息更新。
- 工具开始、工具结束和工具错误。
- SubAgent 委托和完成。
- HITL 中断和恢复。
- 状态更新、rubric evaluation 和最终结果。

Trace 至少记录：

- `run_id`、`thread_id`、tenant、user、模型和版本。
- 输入输出 token、耗时、重试次数和费用。
- 工具名、脱敏参数、结果摘要和错误类别。
- 每次中断、审批人、决策和恢复点。
- 最终结构化结果、验证结果和引用证据。

错误不要都归类成“模型失败”：

| 类型 | 例子 | 处理方式 |
| --- | --- | --- |
| 可重试基础设施错误 | 超时、限流、临时网络错误 | 指数退避、抖动、最大次数 |
| 不可重试配置错误 | 模型不支持 response format | 能力降级或修正配置 |
| 工具输入错误 | 参数缺失、类型不符 | 返回明确 schema 错误，让模型修复一次 |
| 业务拒绝 | 预算不足、无权限 | 不重试，返回确定性结果 |
| 等待人类 | 高风险写操作 | 持久化中断，等待审批 |
| Agent 循环 | 重复调用同一工具 | 步数、时间和费用预算熔断 |

## 10. MCP 工具治理

MCP 统一了工具接入协议，但不会自动解决安全和质量问题。生产中应建立工具目录：

| 字段 | 说明 |
| --- | --- |
| server / tool | 工具来源和稳定标识 |
| owner | 负责人和故障联系人 |
| risk_level | 只读、内部写、高风险外部副作用 |
| auth_scope | 所需用户或服务权限 |
| timeout / retry | 超时和重试策略 |
| idempotency | 是否支持幂等键 |
| data_classification | 参数和返回值的数据级别 |
| approval | 是否需要人工审批 |

还要落实：

- 只连接受信 MCP Server，对 server 和 tool 做 allowlist。
- 工具描述和返回值都视为不可信输入，防止 prompt injection。
- 写工具使用最小权限凭据，不把长期密钥交给模型。
- Schema 变化需要版本管理和回归测试。
- 对返回值设大小上限，大结果写文件或对象存储。
- MCP Server 的进程边界不等于安全沙箱。

## 11. 多模态文件与代码执行边界

`read_file` 可以根据文件类型生成多模态内容块，但最终能否理解 PDF、图片、音视频或 Office 文件，取决于模型供应商和当前模型能力。需要分别测试：

- 支持的 MIME 类型、单文件大小和总请求大小。
- 页数、帧采样、图片分辨率和 OCR 质量。
- 文件是否上传到外部模型服务，是否满足数据合规要求。
- 不支持时是否有文本提取、OCR 或人工处理的降级路径。

代码执行必须区分：

```text
LocalShellBackend = 在宿主机执行，方便但不是安全沙箱
云沙箱 / OpenSandbox = 隔离执行环境，仍需网络、挂载、凭据和资源策略
只实现文件协议的 Backend = 不一定支持 execute
```

安全基线包括 CPU、内存、磁盘、运行时长、进程数、网络出口、挂载目录、环境变量和产物下载限制。Agent 的文件权限规则不能替代这些系统级隔离。

## 12. Rubric 与质量闭环

质量检查建议按成本从低到高分层：

1. 确定性检查：字段、金额、引用、文件是否存在、工具是否调用。
2. 规则检查：业务阈值、权限、审批路径、禁止项。
3. 模型评分：完整性、可读性、论证质量。
4. 人工抽检：高风险任务、低置信度结果和线上漂移样本。

当前版本提供 beta 的 `RubricMiddleware`，可以让 grader 根据 rubric 评价并要求 Agent 修改：

```python
from deepagents.middleware import RubricMiddleware


rubric_middleware = RubricMiddleware(
    model=llm,
    max_iterations=2,
)

agent = create_deep_agent(
    model=llm,
    middleware=[rubric_middleware],
)

result = agent.invoke(
    {
        "messages": [{"role": "user", "content": "生成采购评审报告"}],
        "rubric": (
            "报告必须包含申请编号、证据化风险、审批路径和最终建议；"
            "每个金额必须来自工具结果，不得自行推测。"
        ),
    }
)
```

使用时注意：

- 这是 beta API，升级前要回归测试。
- grader 也是模型，会误判；关键规则仍应使用确定性校验。
- 必须限制最大迭代、token 和总耗时，避免无限自我修改。
- `failed`、`max_iterations_reached`、`grader_error` 不会自动把最后回答改成错误消息，调用方应检查 rubric 状态或事件。
- 评测模型和执行模型可以不同，但要记录各自版本。

## 13. 生产部署与多租户检查清单

### 身份与隔离

- [ ] `user_id`、`tenant_id` 和角色来自服务端鉴权 Context。
- [ ] Checkpoint 的 `thread_id` 绑定租户，读取前再次鉴权。
- [ ] Store、对象存储和向量库都按租户建立 namespace 或强制过滤。
- [ ] SubAgent、MCP Server 和 Sandbox 继承的是最小权限，而不是主服务全部权限。

### 秘密与数据

- [ ] API Key 保存在秘密管理系统，不进入 prompt、Memory 或日志。
- [ ] Trace 和工具参数做字段级脱敏。
- [ ] 明确数据保留期、用户删除、备份恢复和跨境传输策略。
- [ ] 外部模型、云沙箱和 MCP Server 的数据去向已经评审。

### 执行可靠性

- [ ] 使用生产级 Checkpointer 和 Store，不依赖内存实现。
- [ ] 每个任务有步数、时间、token、费用和工具调用预算。
- [ ] 外部写操作使用幂等键，重试不会重复扣款或重复提交。
- [ ] 中断恢复、进程重启、模型超时和 SubAgent 失败都有演练。
- [ ] 并发修改同一业务对象时有版本号、锁或冲突检测。

### 质量与观测

- [ ] 关键任务有固定评测集和版本化 baseline。
- [ ] 同时观察任务成功率、工具错误率、人工接管率、P95 延迟和单任务成本。
- [ ] 最终结论能追溯到工具结果、文件或 RAG 引用。
- [ ] 模型、prompt、skill、tool schema 和依赖升级均可定位和回滚。

## 14. 毕业项目：可恢复的采购评审 Agent

不要再增加模拟工具，直接把现有案例升级成一个小型生产骨架。

### 必做功能

1. 使用 `RunContext` 注入用户、租户和角色。
2. 使用自定义 `DeepAgentState` 保存申请编号和确定性风险结果。
3. 使用 Checkpointer 支持同一 `thread_id` 继续运行。
4. 使用 `CompositeBackend` 分离临时报告和长期记忆。
5. 最终报告写入前触发 HITL，拒绝后可以修改再提交。
6. 使用 `ReviewDecision` 输出结构化结论。
7. 保存 trace，并能从结果追溯到每个风险证据。
8. 构建至少 30 条离线案例，覆盖正常、边界、工具故障和越权请求。

### 验收标准

| 场景 | 必须满足 |
| --- | --- |
| 服务重启后继续 | 使用相同线程能从 checkpoint 恢复 |
| 两个租户同名文件 | 彼此不可见 |
| 用户声称自己是管理员 | 不改变 Context 中的真实权限 |
| 最终报告写入 | 必须收到授权审批 |
| 模型不支持 structured output | 能降级并返回明确状态 |
| 工具连续超时 | 达到预算后停止，不无限循环 |
| 大型工具输出 | 内容卸载，消息中保留摘要和位置 |
| 评测不通过 | 显示具体失败项，不用“感觉不好”代替证据 |

完成这个项目后，才算从“会用 Deep Agents API”进入“能设计 Agent Harness”。

## 15. 仓库内推荐阅读顺序

1. [Python Deep Agents 入门到复杂业务](./python_deep_agents_notes.md)
2. [Deep Agent 核心：LangChain 与 LangGraph](./learn_agent_1/deep_agent_core_langchain_langgraph.ipynb)
3. [Agent 编排工作流](./learn_agent_1/deep_agent_orchestration_workflows.ipynb)
4. [Subgraph 与 Supervisor](./learn_agent_1/deep_agent1_subgraphs_and_supervisor.ipynb)
5. [工具护栏与重试](./learn_agent_1/deep_agent2_tool_guardrails_and_retries.ipynb)
6. [Streaming 与评测](./learn_agent_1/deep_agent3_streaming_and_evaluation.ipynb)
7. [Harness Engineering：从模型能力到可靠 Agent 系统](./harness_engineering.md)
8. [Deep Agents 源码研究与实验手册](./deep_agents_source_research.md)
9. [Deep Agents 可运行示例](../deep_agent_examples/README.md)
10. 回到本文完成毕业项目。

外部文档以当前安装版本对应的官方文档为准：

- [LangChain Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangChain Human-in-the-loop](https://docs.langchain.com/oss/python/langchain/human-in-the-loop)
- [Model Context Protocol](https://modelcontextprotocol.io/)

## 16. 学完生产基线后继续研究什么？

下一阶段应从“功能学习”转向“机制验证”，重点研究：

- `create_deep_agent` 的 Harness 组装顺序和 Middleware 生命周期。
- 自定义 Backend 的协议语义、能力检测与契约测试。
- `isolated`、实验性 `fork`、Compiled 和 Async SubAgent 的状态传播差异。
- Checkpoint 重放、HITL 恢复与外部写操作的幂等边界。
- Summarization、历史卸载和 prompt caching 对任务质量的真实影响。
- AsyncSubAgent 的远程任务状态机、并发一致性和取消语义。
- 故障注入、安全对抗、Provider 兼容矩阵和版本升级门禁。

完整的研究问题、实验方法和验收标准见：[Deep Agents 源码研究与实验手册](./deep_agents_source_research.md)。

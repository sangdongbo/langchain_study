# Deep Agents 源码研究与实验手册

基础教程解决“怎样调用 Deep Agents”，进阶路线解决“怎样把它用于生产”。这份手册继续向下一层研究：

> Deep Agents 的 Harness 怎样组装、状态怎样传播、故障怎样恢复，以及这些行为如何用实验而不是印象证明？

本文按仓库中可正常导入的 `deepagents 0.7.13`、`langchain 1.3.18` 整理。框架仍在快速变化，涉及 beta 或 experimental 的能力必须以当前安装版本源码和回归实验为准。

## 1. 先建立研究地图

可以把 Deep Agents 分成四层：

```text
业务层
  工具、业务规则、结构化结果、审批策略
        |
Harness 层
  Skills、Memory、Filesystem、SubAgent、Middleware、Permissions
        |
运行时层
  LangGraph State、Context、Checkpoint、Store、Interrupt、Streaming
        |
基础设施层
  模型 Provider、Agent Server、MCP、Sandbox、对象存储、观测系统
```

后续研究不要只问“API 怎么写”，而要回答四个问题：

1. 数据从哪里进入，经过哪些层，最后保存在哪里？
2. 失败后从哪里恢复，会不会重复执行外部副作用？
3. 哪些约束只是 Prompt，哪些约束由代码和基础设施强制执行？
4. 如何用 trace、状态快照和自动化实验证明结论？

## 2. 研究优先级

| 优先级 | 主题 | 为什么重要 | 建议产物 |
| --- | --- | --- | --- |
| P0 | Agent 组装和 Middleware 生命周期 | 决定工具、Prompt、状态和审批实际怎样生效 | 钩子顺序实验 |
| P0 | Durable execution 与副作用幂等 | 恢复和重试最容易造成重复写入 | 中断恢复实验 |
| P0 | SubAgent 状态传播 | 多 Agent 问题往往不是模型问题，而是上下文丢失或泄漏 | 状态传播矩阵 |
| P1 | Backend 契约和能力检测 | 自定义存储或 Sandbox 必须遵守统一语义 | Backend contract tests |
| P1 | AsyncSubAgent 远程状态机 | 涉及两个线程、远程运行和状态缓存 | 任务状态机实验 |
| P1 | 上下文压缩和信息损失 | 长任务质量取决于保留了什么，而不只是 token 数 | 摘要保真度评测 |
| P1 | 模型适配和 Harness Profile | 不同 Provider 的工具、文件和结构化输出能力不同 | Provider 能力矩阵 |
| P2 | 并发、一致性和资源治理 | 单用户演示无法暴露生产竞争条件 | 并发与限额实验 |
| P2 | 安全对抗和故障注入 | 正常路径通过不代表系统可靠 | chaos / red-team 用例集 |
| P2 | 升级兼容性 | Deep Agents API 变化快 | 版本升级门禁 |

研究顺序建议先做 P0。没有弄清状态传播和重放语义之前，不要急着增加更多 SubAgent 或工具。

## 3. `create_deep_agent` 到底组装了什么

`create_deep_agent(...)` 不是简单的 ReAct 循环构造器。当前版本会根据参数和模型 Profile 组装一条 Harness middleware 链。

主 Agent 的主要顺序是：

```text
SkillsMiddleware（配置 skills 时）
FilesystemMiddleware
SubAgentMiddleware（存在同步子 Agent 时）
SummarizationMiddleware
PatchToolCallsMiddleware
AsyncSubAgentMiddleware（存在远程异步子 Agent 时）
用户 middleware
Harness Profile 的额外 middleware
Prompt caching middleware
MemoryMiddleware（配置 memory 时）
HumanInTheLoopMiddleware（配置 interrupt_on 时）
```

这个顺序值得研究，因为 middleware 可以：

- 在模型调用前修改 system prompt 和工具列表。
- 在模型或工具外层包裹重试、缓存、日志和权限判断。
- 读取或更新 State。
- 短路模型调用或工具调用。
- 把普通返回值改造成 `Command`，进而修改图状态。

最小研究任务：

1. 给每个 hook 记录时间戳和调用序号。
2. 分别运行 `invoke()` 与 `ainvoke()`。
3. 让模型产生一次普通回答和一次工具调用。
4. 对照 trace 画出真实执行顺序。

通过标准：能够解释同一个 middleware 为什么在同步调用中正常、在异步调用中却可能抛出 `NotImplementedError`。

## 4. Middleware 生命周期与组合语义

`AgentMiddleware` 的核心扩展点包括：

| Hook | 作用范围 | 常见用途 |
| --- | --- | --- |
| `before_agent` / `after_agent` | 整个 Agent 运行 | 初始化、最终审计、汇总指标 |
| `before_model` / `after_model` | 每次模型节点 | 修改状态、检查模型输出 |
| `wrap_model_call` | 包裹模型请求 | 回退模型、重试、缓存、动态工具 |
| `wrap_tool_call` | 包裹工具执行 | 权限、幂等、超时、日志、错误转换 |
| `a...` 对应方法 | 异步调用路径 | 异步 I/O 和远程服务 |

多个 wrapper 组合时，列表中靠前的 middleware 是更外层的 wrapper。研究时要特别验证：

- 入栈顺序和出栈顺序是否符合预期。
- wrapper 是否错误地调用 `handler` 多次。
- 重试一个写工具是否产生重复业务操作。
- sync hook 和 async hook 是否具有一致行为。
- middleware 写入的 State 字段是否声明在 `state_schema` 中。
- trace 是否意外记录敏感 prompt、token 或工具参数。

一个只用于观察顺序的骨架：

```python
from langchain.agents.middleware import AgentMiddleware


class LifecycleProbe(AgentMiddleware):
    def __init__(self, events: list[str]) -> None:
        self.events = events

    def before_agent(self, state, runtime):
        self.events.append("before_agent")

    def before_model(self, state, runtime):
        self.events.append("before_model")

    def wrap_model_call(self, request, handler):
        self.events.append("model:enter")
        response = handler(request)
        self.events.append("model:exit")
        return response

    def wrap_tool_call(self, request, handler):
        self.events.append(f"tool:{request.tool_call['name']}:enter")
        response = handler(request)
        self.events.append(f"tool:{request.tool_call['name']}:exit")
        return response

    def after_agent(self, state, runtime):
        self.events.append("after_agent")
```

如果生产系统同时支持 `invoke()` 和 `ainvoke()`，就要实现并测试两套 wrapper；只实现同步版本不能自动保证异步路径可用。

### 4.1 `SkillsMiddleware` 的发现、缓存和按需读取

`SkillsMiddleware` 的“加载”分两层，源码研究时不要混为一谈：

```text
before_agent
  -> backend.ls(source)
  -> download <skill>/SKILL.md
  -> 解析 frontmatter
  -> state["skills_metadata"]

wrap_model_call
  -> system prompt 中追加 name / description / path

模型选中 Skill
  -> read_file(path)
  -> 完整正文进入消息上下文
```

第一层会读取 backend 文件以解析 metadata，但不会把完整正文直接注入模型；第二层才是 progressive disclosure。`skills_metadata` 是私有 Middleware State，并以字段是否已经存在作为缓存命中条件，所以空结果也会缓存。同一 checkpointed thread 修改 `files` 后不会自动重扫。

研究时至少验证：

- 固定目录 Skill 与 `StateBackend.files` Skill 的 prompt 形态是否相同。
- 新 thread 是否按预期得到不同 Skill 集合。
- 同一 thread 新增、修改、删除 Skill 后是否出现陈旧 metadata。
- 多 source 同名 Skill是否由后加载的 source 覆盖。
- `allowed-tools` 是否只是提示 metadata，而非强制工具权限。
- 子 Agent 是否因为 `skills_metadata` 的私有属性而重新建立自己的 Skill 索引。

完整实验说明和可运行入口见：[基于 State 的动态 Skills](../../deep_agent_examples/examples/dynamic_skills/README.md)。

SubAgent 研究也应拆开验证，不要把同步嵌套 runnable 和远程任务状态机混为一谈：

- [声明式 SubAgent：isolated、fork 与 State 传播](../../deep_agent_examples/examples/declarative_subagent/README.md)
- [CompiledSubAgent：复用现成 Agent 与 StateGraph](../../deep_agent_examples/examples/compiled_subagent/README.md)
- [AsyncSubAgent：远程 thread、run 与后台任务状态机](../../deep_agent_examples/examples/async_subagent/README.md)

## 5. BackendProtocol 契约研究

`BackendProtocol` 统一的是文件语义，不代表所有 backend 都能执行命令。当前协议分两层：

```text
BackendProtocol
  ls / read / grep / glob / write / edit
  可选 delete / upload_files / download_files

SandboxBackendProtocol
  继承全部文件能力
  增加 id / execute / aexecute
```

同步文件方法的默认异步实现通常通过 `asyncio.to_thread(...)` 包装。它能避免阻塞事件循环，但取消等待不一定能终止已经在线程中运行的同步任务。自定义远程 backend 更适合提供真正的异步实现。

### 必做契约实验

| 行为 | 应验证内容 |
| --- | --- |
| 路径 | 输入和返回是否统一为绝对 POSIX 路径 |
| `read` | offset、limit、行号和 `next_offset` 是否一致 |
| `grep` | pattern 是字面量，不是正则；`max_count` 是否全局生效 |
| `glob` | `*`、`**`、前导 `/`、隐藏文件语义是否一致 |
| `write` | 覆盖行为和错误对象是否稳定 |
| `edit` | 唯一匹配、`replace_all`、零匹配是否正确 |
| delete | 未实现时是否正确报告“不支持”，递归删除是否有权限保护 |
| 批量传输 | 部分成功时是否按输入顺序逐项返回错误 |
| execute | 非零退出码、超时、输出截断如何表示 |

一个容易误判的点：命令确实运行后，即使退出码非零，工具消息也不一定标记成 error。判断命令成功必须读取 `ExecuteArtifact.exit_code` 或 `ExecuteResponse.exit_code`，不能只看消息状态。

### 自定义 Backend 的完成标准

- 相同输入在 sync / async 方法上产生一致结果。
- 所有错误都转换成稳定的结果对象，不把底层异常文本直接泄漏给模型。
- 大结果有截断标记，完整产物有可追踪位置。
- 权限判断使用规范化后的绝对路径。
- 路径穿越、符号链接和 route prefix 均有专门用例。
- 并发写同一文件的行为有明确约定，而不是依赖偶然顺序。

## 6. SubAgent 上下文与状态传播

同步子 Agent 至少要研究两个模式：

| 模式 | 输入上下文 | 适用场景 | 风险 |
| --- | --- | --- | --- |
| `isolated` | 委托描述和允许传播的 State | 独立调查、控制 token、最小披露 | 主 Agent 漏写上下文会导致结果空泛 |
| `fork` | 父 Agent 的有效会话和更多 State | 需要完整对话背景的延续任务 | 上下文更大，泄漏和递归委托风险更高 |

当前版本的 `mode="fork"` 是 experimental。声明式 fork 会重建父 Agent 的 prompt-producing middleware，并继承父会话；它不能再单独声明 `skills`。`CompiledSubAgent` 已经编译完成，不会自动继承主 Agent 的模型、middleware、state schema 或 interrupt 配置。

状态传播还要验证：

- `messages`、`todos`、`structured_response` 怎样特殊处理。
- Middleware 私有 State 是否被隔离。
- 子 Agent 返回的普通 State 字段是否会合并回父 Agent。
- Structured response 是否会序列化为父 Agent 看到的 `ToolMessage`。
- 父 Agent 做过 summarization 后，fork 收到的是原始历史还是有效压缩历史。
- 子 Agent 是否能再次调用 `task`，以及框架如何阻止递归失控。

建议建立状态传播矩阵，每个字段只填四种结果：`继承`、`不继承`、`转换`、`实验性`。升级版本后重新运行，不要长期依赖口头结论。

## 7. AsyncSubAgent 是远程任务状态机

`AsyncSubAgent` 不是本进程里的 `asyncio.gather`。它通过 Agent Protocol / LangGraph SDK 在远程服务创建 thread 和 run，并在父 Agent State 的 `async_tasks` 中保存任务元数据。

当前工具生命周期是：

```text
start_async_task
        |
        +--> check_async_task
        +--> list_async_tasks
        +--> update_async_task
        +--> cancel_async_task
```

重点研究：

1. `task_id` 与远程 `thread_id` 的对应关系。
2. State 中的缓存状态与远程实时状态何时可能不一致。
3. 父 Agent 重启后，checkpoint 是否足以恢复任务追踪。
4. `update_async_task` 中断旧 run 并启动新 run 时，旧结果如何处理。
5. cancel、timeout、error、interrupted 等终态怎样呈现给用户。
6. 远程服务不可达时，是返回缓存状态还是明确未知状态。
7. 自托管认证 header 如何按用户隔离并避免写入 trace。

建议画出明确状态机：

```text
created -> running -> success
                   -> error
                   -> timeout
                   -> interrupted
                   -> cancelled
```

不要轮询已经进入终态的任务。也不要把聊天记录中上一次看到的状态当成实时状态，展示前应重新查询。

## 8. Durable execution、重放与幂等

Checkpoint 能保存图状态，但“保存状态”不等于“外部副作用恰好执行一次”。进程可能在下面这个窗口崩溃：

```text
调用付款 API 成功
        |
进程崩溃，尚未提交新的 checkpoint
        |
恢复后重新执行付款工具
```

因此，高风险写工具应把幂等放在业务系统边界：

```python
def submit_purchase(request_id: str, idempotency_key: str) -> dict:
    """相同 key 重试时返回第一次提交的结果，不重复创建采购单。"""
    ...
```

需要研究的恢复语义：

- interrupt 前后分别保存了什么状态。
- 同一个 `thread_id` 重复 invoke 会追加、恢复还是冲突。
- tool retry、node retry 和用户重试分别在哪一层发生。
- 外部调用成功但 checkpoint 失败时如何对账。
- 人工批准后参数是否仍是审批时看到的那一份。
- 过期审批、撤销审批和重复 resume 如何处理。

通过标准：故障注入发生在任意一步时，业务对象最多创建一次，审计日志能说明发生过哪些尝试。

## 9. 上下文压缩的保真度

Summarization 不是单纯删消息。当前实现还涉及：

- token 或消息数量触发阈值。
- 保留最近消息的 keep 策略。
- 旧工具参数截断。
- 历史写入 `/conversation_history/{session_id}.md`。
- 内联媒体卸载为可引用文件。
- fork 子 Agent 对 summarization event 的应用。

建议建立“摘要前后不变量”：

- 用户目标没有改变。
- 已确认的事实、金额、ID 和截止时间仍存在。
- 未完成待办和阻塞原因仍存在。
- 工具执行成功/失败状态没有颠倒。
- 引用来源仍能定位。
- 审批决定和批准参数仍能审计。

评测不要只比较摘要文字相似度，应让同一批任务分别在“未压缩”和“发生压缩”条件下运行，对比最终任务成功率、事实遗漏率、重复工具调用率和 token 成本。

## 10. Harness Profile 与模型可移植性

Harness Profile 可以针对模型调整：

- `base_system_prompt` 和 `system_prompt_suffix`。
- 工具描述覆盖。
- 工具和 middleware 可见性。
- 默认 general-purpose subagent。
- 额外 middleware。

它适合解决 Provider 差异，但不应成为隐藏业务逻辑的位置。建议维护模型能力矩阵：

| 能力 | 需要实测的问题 |
| --- | --- |
| Tool calling | 并行工具、参数校验、错误修复是否稳定 |
| Structured output | ProviderStrategy / ToolStrategy 哪个可用 |
| 文件输入 | PDF、图片、Office、音视频支持范围 |
| 上下文窗口 | 实际输入上限、超限错误、摘要触发点 |
| Prompt caching | 哪些前缀可缓存，命中率和节省是多少 |
| Streaming | 工具事件和 structured response 是否完整 |
| 数据保留 | Provider 是否存储请求，能否关闭 |

`HarnessProfile` 目前仍是 beta。每个 Profile 必须绑定模型标识、依赖版本和回归结果，不能只凭模型名称猜测能力。

## 11. 并发与一致性

生产研究至少覆盖三种并发：

1. 同一个用户的不同 thread 同时修改长期 Store。
2. 同一个 `thread_id` 被两个请求同时恢复。
3. 多个 SubAgent 同时写同一文件或业务对象。

需要明确：

- 谁拥有 thread 的写权限。
- checkpoint 是否有版本号或冲突检测。
- Store 更新是覆盖、合并还是 compare-and-set。
- `CompositeBackend` 的不同 route 是否具有不同一致性等级。
- 长任务取消后，已经启动的外部工具或远程 Agent 是否仍在运行。
- 限流按用户、租户、模型、工具还是 sandbox 计算。

Agent 层不要自行猜测冲突结果。发生版本冲突时，应重新读取可信状态、明确报告冲突，或进入人工处理。

## 12. 安全研究不能只测拒绝词

建议建立下面的安全用例集：

| 攻击面 | 示例 |
| --- | --- |
| Prompt injection | 文件内容要求忽略系统规则并泄漏其他文件 |
| Path traversal | `../`、符号链接、route prefix 绕过 |
| Tool description poisoning | MCP Server 返回诱导性描述 |
| Confused deputy | 普通用户借高权限工具替自己执行操作 |
| Secret exfiltration | 让 Agent 读取环境变量、日志或 Memory 中的密钥 |
| Resource exhaustion | 无限循环、超大输出、压缩炸弹、fork bomb |
| Approval substitution | 批准后替换参数或目标资源 |
| Cross-tenant access | 猜测别人的 thread、task、file、namespace ID |

每个用例都要区分：

- 模型是否拒绝。
- 工具层是否强制拒绝。
- 基础设施是否隔离。
- trace 是否留下证据。

真正的安全结论来自后三项，而不是模型恰好说了“不”。

## 13. 故障注入实验

正常路径评测之后，按层注入故障：

| 注入点 | 预期行为 |
| --- | --- |
| 模型 429 / timeout | 有界重试或切换模型，不重复写工具 |
| 工具返回畸形 JSON | 校验失败并有限修复 |
| Backend 写入失败 | State 不宣称文件已保存 |
| Checkpoint 提交失败 | 可检测、可重试、外部副作用可对账 |
| Store 暂时不可用 | 临时任务可继续或明确降级，不能伪造记忆 |
| Sandbox 超时 | 终止或隔离遗留进程，记录截断输出 |
| SubAgent 无最终消息 | 父 Agent 收到可诊断错误 |
| AsyncSubAgent 服务断开 | 区分缓存状态与实时未知状态 |
| Grader 误判 | 确定性规则优先，人工可以覆盖 |

故障注入的价值是验证恢复边界，而不是追求“所有错误都自动重试”。业务拒绝、权限拒绝和 schema 不兼容通常不应该盲目重试。

## 14. 测试金字塔

Deep Agents 项目可以采用下面的测试层次：

```text
少量端到端真实模型评测
        |
录制或 Fake Model 的 Agent 轨迹测试
        |
Middleware / Backend / Tool 契约测试
        |
纯业务规则单元测试
```

分别检查：

- **业务规则**：金额、权限、路由等确定性逻辑。
- **工具契约**：schema、错误对象、幂等和超时。
- **轨迹**：调用了什么、顺序是否正确、是否越权。
- **最终结果**：结构化字段、证据和引用。
- **恢复路径**：interrupt、重试、重启和取消。
- **统计质量**：固定数据集上的成功率、成本和 P95 延迟。

不要把所有测试都依赖真实模型。模型评测昂贵且有波动，低层契约应尽量使用确定性输入完成。

## 15. 升级兼容性研究

本仓库已经出现过 `deepagents` 与 `langchain` 版本组合不兼容。升级前应自动记录：

```python
from importlib.metadata import version
from inspect import signature

from deepagents import create_deep_agent


print("deepagents", version("deepagents"))
print("langchain", version("langchain"))
print(signature(create_deep_agent))
```

升级门禁至少包括：

- 包可以正常导入。
- `create_deep_agent` 参数和默认行为没有意外变化。
- Middleware 顺序快照符合预期。
- SubAgent 状态传播矩阵通过。
- Backend contract tests 通过。
- 中断恢复和幂等实验通过。
- Provider 能力矩阵重新验证。
- beta / experimental API 的行为重新阅读源码。

不要只看语义化版本号。框架、Provider SDK 和模型服务三者任一变化都可能改变行为。

## 16. 推荐的五个研究项目

### 项目一：Harness 可视化探针

记录每个 middleware hook、模型调用、工具调用和 State 更新，生成一条可读时间线。

验收：同步、异步、普通回答、工具调用和 HITL 五种路径都能解释。

### 项目二：Backend 兼容性套件

对 `StateBackend`、`FilesystemBackend`、`StoreBackend`、本地 Sandbox 和云 Sandbox 运行同一组契约用例。

验收：差异都有文档说明，不用 backend 名称推测能力。

### 项目三：SubAgent 上下文实验室

对比 `isolated`、`fork`、`CompiledSubAgent`、`AsyncSubAgent` 在消息、State、Skills、权限和 structured response 上的行为。

验收：形成版本化状态传播矩阵，并能检测上下文泄漏。

### 项目四：可恢复副作用工作流

构造“审批后提交采购单”流程，在每个 checkpoint 前后模拟崩溃。

验收：无论从哪里恢复，都不会重复创建采购单，且审批参数不可被替换。

### 项目五：上下文压力与质量基准

逐步增加消息、工具大输出、文件和媒体，观察 truncation、offloading、summarization 和 prompt caching。

验收：得到质量、token、延迟、费用四条曲线，并确定本项目的安全阈值。

## 17. 怎样判断已经研究够了

不是把所有源码读完，而是能回答下面这些问题：

- 当前请求经过哪些 middleware，顺序是什么？
- 某个字段属于 State、Context、Checkpoint 还是 Store？
- 父子 Agent 之间哪些信息会传播，哪些不会？
- backend 支持文件操作还是也支持 execute？
- 故障恢复会不会重复调用外部写接口？
- 摘要后丢失了什么，怎样量化？
- 远程异步任务的实时状态从哪里获得？
- 模型更换后哪些能力必须重新测试？
- 安全限制由 Prompt、工具层还是基础设施执行？
- 一次失败能否从 trace 和状态快照定位到具体层？

能够用实验和证据回答这些问题，才算真正掌握了 Deep Agents，而不只是会调用 `create_deep_agent()`。

## 18. 继续阅读

- [Deep Agents 可运行示例：Studio、LangSmith 与 Sandbox](../../deep_agent_examples/README.md)
- [Deep Agents 进阶学习路线](./deep_agents_advanced_learning.md)
- [Harness Engineering：从模型能力到可靠 Agent 系统](./harness_engineering.md)
- [LangChain Deep Agents](https://docs.langchain.com/oss/python/deepagents/overview)
- [LangGraph Persistence](https://docs.langchain.com/oss/python/langgraph/persistence)
- [LangChain Middleware](https://docs.langchain.com/oss/python/langchain/middleware)
- [Agent Protocol](https://github.com/langchain-ai/agent-protocol)
- [Model Context Protocol](https://modelcontextprotocol.io/)

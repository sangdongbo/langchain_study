# Agent 与子 Agent 生命周期

Deep Agents 没有单独的“生命周期管理器”。生命周期由 LangGraph 的图执行、Agent Middleware、工具循环、checkpoint，以及子 Agent 的调用方式共同决定。

本目录提供两个专门的可运行示例：

- `lifecycle_agent`：普通 Agent 生命周期。
- `subagent_lifecycle_agent`：父 Agent 与声明式同步子 Agent 生命周期。

已有的 `compiled_subagent_agent`、`async_subagent_agent` 和 `remote_research_agent` 分别覆盖预编译子图与远程后台任务。

每种子 Agent 的详细机制已经拆分：

- [声明式 SubAgent](../declarative_subagent/README.md)
- [CompiledSubAgent](../compiled_subagent/README.md)
- [AsyncSubAgent](../async_subagent/README.md)

## 1. 普通 Agent 生命周期

Graph 在 Python 模块加载时构建并编译；每次用户输入触发一次 run。一次正常、有工具调用的 run 大致如下：

```text
构建并编译 Graph
        │
        ▼
载入输入与 thread checkpoint
        │
        ▼
before_agent                         每个 run 一次
        │
        ▼
before_model → wrap_model_call → 模型 → after_model
        │                                  │
        │                         没有 tool_calls ─────┐
        │                                  │           │
        │                           有 tool_calls       │
        │                                  ▼           │
        └──────── tools ← wrap_tool_call ← 工具         │
                                                           ▼
                                                      after_agent
                                                           │
                                                           ▼
                                                  最终 State / checkpoint
```

关键点：

- `before_agent` 和 `after_agent` 面向整个 run；`before_model` 与 `after_model` 面向每一轮模型循环。
- `wrap_model_call`、`wrap_tool_call` 是调用包装器，可做重试、计量、修改请求或短路；本示例只透传，用于产生清晰的 LangSmith span。
- 工具返回后会再次进入 `before_model`。因此一次“模型选择工具 → 工具执行 → 模型生成答案”通常有两组 model hooks。
- checkpoint 保存的是 Graph State，不是 Python Middleware 实例。使用同一 `thread_id` 发起新一轮输入时，会从已保存 State 继续，但这是一个新 run，`before_agent` 会再次执行。
- interrupt 会在当前节点暂停并写入 checkpoint；resume 从暂停点继续，不会从 `before_agent` 重跑。只有真正走到正常出口才执行 `after_agent`。
- 未处理异常或取消可能直接终止 run，不能把 `after_agent` 当成一定执行的 `finally`。必须释放的外部资源应使用工具自身的上下文管理或服务端租约。

### 运行并观察

在 Studio 选择 `lifecycle_agent`，或运行：

```powershell
uv run deep-agent-example lifecycle --thread-id lifecycle-001
uv run python examples/lifecycle/run.py --kind agent
```

不需要 API Key 的同步/异步确定性测试：

```powershell
uv run python examples/lifecycle/test.py
```

典型的 `lifecycle_events` 是：

```text
01 agent.before_agent
02 agent.before_model
03 agent.after_model(tool_calls=1)
04 agent.before_model
05 agent.after_model(tool_calls=0)
06 agent.after_agent
```

事件保存在 State 中；`AgentLifecycleProbe.wrap_model_call` 和 `AgentLifecycleProbe.wrap_tool_call` 则在 LangSmith trace 中查看。模型不遵循提示、产生额外工具调用时，循环次数会相应增加，这是正常现象。

## 2. 声明式同步 SubAgent

`SubAgent` spec 在父 Graph 创建时被编译，但子 Agent 只有在父 Agent 调用 `task` 工具时才开始一次执行：

```text
父 Agent model
    │  task(description, subagent_type)
    ▼
准备子 Agent State
    │
    ▼
子 Agent before_agent → 模型/工具循环 → after_agent
    │
    ▼
最终 AIMessage 转成父 Agent 的 ToolMessage
    │
    ▼
允许回传的 State 字段合并到父 State
    │
    ▼
父 Agent 继续下一轮 model
```

默认 `mode="isolated"`：

- 子 Agent 的 `messages` 只有本次委托描述，不会获得父对话全文。
- 父 State 中可传播的公共字段仍会传入；`messages`、`todos`、`structured_response` 和私有 Middleware State 会被排除。
- `task` 会阻塞到子 Agent 完成。每次调用都是一次临时执行，没有独立的远程 thread。
- 子 Agent 最终的非空 `AIMessage` 会成为父 Agent 的 `ToolMessage`；其他允许传播的 State 字段也会通过 reducer 合并回父 State。

实验性的 `mode="fork"` 会带入父 Agent 的有效对话和更多 State，并重建父级提示上下文。它适合强依赖会话上下文的委托，但更容易造成上下文膨胀、缓存失效和不必要的信息暴露；普通任务优先使用 `isolated` 并在 description 中写全上下文。

### 运行并观察

在 Studio 选择 `subagent_lifecycle_agent`，或运行：

```powershell
uv run deep-agent-example subagent-lifecycle --thread-id subagent-lifecycle-001
uv run python examples/lifecycle/run.py --kind subagent
```

Studio State 中分别查看：

- `parent_lifecycle_events`
- `child_lifecycle_events`

LangSmith 中展开父级 `task` 调用，可看到带有 `ls_agent_type="subagent"` metadata 的子 Agent run，以及 `ChildLifecycleProbe.*` spans。该示例只委托一次；事件 reducer 会去掉同步子 Agent 回传公共 State 时产生的重复项。

## 3. CompiledSubAgent

`CompiledSubAgent` 的生命周期与同步 `task` 相同，但 runnable 在注册前已经由应用自行构建：

```text
应用预编译 runnable
  → 注册 CompiledSubAgent
  → 父 Agent 调用 task
  → runnable.invoke / ainvoke
  → 读取 structured_response 或最后一个非空 AIMessage
  → 合并允许回传的 State
```

它不会自动继承父 Agent 的 model、Middleware、State schema、interrupt 配置或 checkpointer。若预编译 runnable 需要这些能力，必须在编译它时自行配置；是否拥有独立持久化也取决于该 runnable 自己是否配置 checkpointer。

运行现有示例：

```powershell
uv run deep-agent-example compiled
```

## 4. AsyncSubAgent

`AsyncSubAgent` 不是父进程内的一次嵌套调用，而是 Agent Protocol 服务上的独立 thread 与后台 run：

```text
注册 AsyncSubAgent spec
        │
        ▼
start_async_task
        │
        ├─ 创建远程 thread
        ├─ 创建远程 run
        └─ 父 State.async_tasks 保存 task_id/thread_id/run_id
        │
        ▼
父 Agent 立即返回             远程 Agent 独立运行
        │                            │
        ├─ check_async_task ─────────┤
        ├─ list_async_tasks ─────────┤
        ├─ update_async_task ── 同 thread 新 run，旧 run 被 interrupt
        └─ cancel_async_task ── 取消当前 run
                                     │
                                     ▼
                 success / error / timeout / interrupted / cancelled
```

父 checkpoint 只保存任务追踪元数据；远程 Agent 的完整消息、State 和 checkpoint 属于远程 thread。`cancel_async_task` 取消 run，但不会删除远程 thread。生产系统应另外定义 thread 保留期、过期任务清理和幂等策略。

先启动本地 Agent Server，再运行：

```powershell
uv run langgraph dev --host 127.0.0.1 --port 2024
uv run deep-agent-example async --thread-id async-001
```

在 LangSmith 中，父侧重点是 `start_async_task` 等工具 span；远程 `remote_research_agent` 是独立执行，应使用 `task_id`、`thread_id`、`run_id` 和项目过滤器关联两侧，而不要假设它一定显示为父 trace 中的同步嵌套节点。

## 5. State、checkpoint 与资源归属

| 类型 | 执行位置 | 父调用是否阻塞 | 状态归属 | 结束或恢复方式 |
| --- | --- | --- | --- | --- |
| 普通 Agent | 当前 Graph | 是 | 当前 thread checkpoint | 完成、interrupt/resume、错误或取消 |
| `SubAgent` | 父 run 内的临时 runnable | 是 | 临时子 State；允许字段合并回父 State | 返回最终报告后结束 |
| `CompiledSubAgent` | 父 run 内的自有 runnable | 是 | 由 runnable schema/checkpointer 决定 | runnable 返回；可有自己的 checkpoint |
| `AsyncSubAgent` | Agent Protocol 服务 | 否 | 独立远程 thread；父侧只存追踪元数据 | check/update/cancel；由远程服务持久化 |

查看干净的一次生命周期时请新建 `thread_id`；复用 thread 会保留此前的 lifecycle event 和其他 State，这正是 checkpoint 语义，而不是探针泄漏。

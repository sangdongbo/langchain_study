# AsyncSubAgent：远程 thread、run 与后台任务状态机

`AsyncSubAgent` 通过 Agent Protocol / LangGraph SDK 在远程服务创建独立 thread 和 run。它不是 `asyncio.gather()`，也不是同步 `task` 的异步语法版本。

对应文件：

- 真实 Agent Server 与 LangSmith：[run.py](run.py)
- Fake Agent Protocol 测试：[test.py](test.py)
- 远程目标 Graph：`deep_agent_examples.graphs:remote_research_agent`

## 1. 最小配置

```python
remote: AsyncSubAgent = {
    "name": "remote-procurement-researcher",
    "description": "Researches supplier risk in the background.",
    "graph_id": "remote_research_agent",
    "url": "http://127.0.0.1:2024",
}

parent = create_deep_agent(
    model=model,
    subagents=[remote],
)
```

字段含义：

| 字段 | 必填 | 含义 |
| --- | --- | --- |
| `name` | 是 | 父模型选择的远程 Agent 类型 |
| `description` | 是 | 告诉父模型何时启动它 |
| `graph_id` | 是 | 远程 assistant/Graph ID |
| `url` | 否 | Agent Protocol 地址；省略时使用本地 ASGI transport |
| `headers` | 否 | 自托管服务认证 header |

省略 `url` 的 ASGI transport 只支持异步父入口。同步 `invoke()` 需要一个可访问的 URL。

## 2. 两套相互独立的生命周期

```text
父 Agent thread                         远程 Agent thread
────────────────                       ──────────────────
父模型调用 start_async_task
        │
        ├──── threads.create ─────────> 创建 remote thread
        ├──── runs.create ────────────> 创建 remote run
        │                                  │
        │                                  ├─ 模型/工具循环
async_tasks 保存 tracking metadata         ├─ checkpoint
父 Agent 立即继续/返回                      └─ success/error/...
        │
        ├──── check ───────────────────> 查询 run / thread values
        ├──── update ──────────────────> 同 thread 创建新 run
        └──── cancel ──────────────────> 取消当前 run
```

父 checkpoint 不是远程 checkpoint 的副本。父级只保存怎样找到远程任务，完整 messages、文件、HITL 和执行状态属于远程 thread。

## 3. 父 State 的 `async_tasks`

每个 task 记录：

```python
{
    "task_id": "...",       # 当前实现与 remote thread_id 相同
    "agent_name": "remote-procurement-researcher",
    "thread_id": "...",
    "run_id": "...",
    "status": "running",
    "created_at": "...Z",
    "last_checked_at": "...Z",
    "last_updated_at": "...Z",
}
```

`async_tasks` 使用按 `task_id` 合并的 reducer，所以检查、更新和取消只覆盖对应任务，不会抹掉其他后台任务。

父 Agent 想跨多轮继续管理任务，必须满足：

- 有 checkpointer。
- 后续调用复用同一父 `thread_id`。
- State 中仍存在对应 `async_tasks`。

只有远程 `task_id`、但启动了一个全新的无状态父 Agent，并不足以调用内置 `check_async_task`，因为工具会先在父 State 中验证这是一个已追踪任务。

## 4. 五个管理工具

### `start_async_task`

```text
校验 subagent_type
-> 创建 remote thread
-> 在该 thread 创建 run
-> task_id = thread_id
-> status=running 写入父 async_tasks
-> 立即返回 task_id
```

启动后应把 task ID 告诉用户并停止，不要立即循环检查。

### `check_async_task`

```text
从父 State 找 tracked task
-> runs.get(thread_id, run_id)
-> success 时读取 threads.get(...).values
-> 取远程最后一条 message 作为 result
-> 更新父 cached status / checked time
```

远程状态查询失败和远程 run 业务失败是两种不同情况，不能都报告成“任务失败”。

### `update_async_task`

```text
同一个 remote thread_id
-> runs.create(new input, multitask_strategy="interrupt")
-> 当前旧 run 被中断
-> 父 task_id 不变
-> run_id 替换为新 run
-> status 回到 running
```

这不是修改旧 run 的内存，而是在同一会话 thread 上追加消息并创建新 run。

### `cancel_async_task`

取消父 State 记录的当前 `run_id`，再把缓存状态写成 `cancelled`。取消 run 不等于删除 remote thread，也不保证已经提交到外部系统的副作用会回滚。

### `list_async_tasks`

列出父 State 中已追踪任务并刷新 live status。对已知 terminal status，列表逻辑可以直接使用缓存，避免无意义远程请求。过滤首先基于缓存状态，因此刚在远端结束、父侧仍缓存 running 的任务，按 success 过滤时可能暂时看不到；先刷新或按 all 查询。

## 5. 状态集合与终止条件

常见状态：

```text
running
  ├─ success
  ├─ error
  ├─ timeout
  ├─ interrupted
  └─ cancelled
```

生产代码不要只判断 `success/cancelled`。远程服务、队列或平台版本可能返回其他合法状态；父 State 当前使用字符串保存状态就是为了容纳 SDK 的实际返回值。

## 6. update、cancel 与竞态

需要明确几个竞态：

- check 返回 running 后，远程任务可能立刻 success；缓存只是观察时刻的快照。
- update 使用 interrupt 策略创建新 run，旧 run 的外部工具可能已经产生副作用。
- cancel 请求成功不等于所有外部进程已经停止；Sandbox 和工具必须有自己的取消语义。
- 两个父请求同时 update 同一 task 时，哪个 run_id 成为当前追踪对象需要并发控制。
- 多次 start 可能创建重复远程任务；业务层应提供幂等 key，而不是只靠模型“不要重复调用”的提示。

## 7. 不继承父 Agent 的能力

远程 Graph 是独立部署单元，不自动继承父级：

- model
- tools
- system prompt
- middleware
- skills
- State schema
- permissions / `interrupt_on`
- checkpointer
- Store

这些必须在 `remote_research_agent` 自己的构建和部署中配置。父 Agent 的文件权限不能保护远程 Graph；反过来也一样。

## 8. 真实本地运行

终端一启动 Agent Server：

```powershell
cd deep_agent_examples
uv run langgraph dev --host 127.0.0.1 --port 2024
```

终端二只启动任务：

```powershell
uv run python examples/async_subagent/run.py
```

显式等待 5 秒并做一次检查：

```powershell
uv run python examples/async_subagent/run.py --check-after 5
```

示例故意没有实现无限轮询。`--check-after` 只执行一次检查，并且同一个 Python 进程保留 `InMemorySaver`，所以父 State 中仍有 task tracking metadata。

如果进程退出，示例的内存 checkpoint 也消失。生产系统应使用持久化 checkpointer 或直接通过 LangGraph Server 的同一父 thread 继续对话。

## 9. LangSmith 中怎样关联父远程两侧

同步 SubAgent 往往显示为父 trace 下的嵌套 run；AsyncSubAgent 的远程执行拥有独立 thread/run，不应假设它一定成为父 trace 的同步子节点。

父 trace 重点看：

- `start_async_task`、`check_async_task` 等工具 span。
- `task_id`、`thread_id`、`run_id`。
- 父 State 中缓存状态何时更新。

远程 trace 重点看：

- `remote_research_agent` 的完整模型和工具轨迹。
- 远程 thread/run ID。
- 中断、取消和失败原因。

生产中应把关联 ID 写进两侧 trace metadata。示例父侧写入：

```text
subagent_kind=async
remote_graph_id=remote_research_agent
agent_server_url=...
entrypoint=examples/async_subagent/run.py
```

## 10. 认证与数据安全

- 托管 LangGraph/LangSmith Deployment 通常通过 SDK 环境变量认证。
- 自托管服务可在 spec `headers` 中提供认证 header，但不要把 token 写进代码或 trace。
- 远程服务必须重新做 tenant、thread、assistant 权限检查；不能因为请求来自父 Agent 就默认可信。
- `task_id` 不是授权凭证。能猜到 ID 不应等于能读取任务。
- 跨租户部署必须隔离 checkpoint、Store、Sandbox、日志和 trace。

## 11. 不启动服务器的测试

```powershell
uv run python examples/async_subagent/test.py
```

测试用假的 Agent Protocol client 真实执行 Middleware 工具，验证：

- start 创建 remote thread/run 并写父 tracking State。
- check 读取远程 result 并把缓存状态更新为 success。
- update 保持 task/thread ID，创建新 run，并使用 interrupt 策略。
- cancel 精确取消当前新 run，并记录 terminal status。

测试不需要模型 Key、Agent Server、LangSmith 或网络。

## 12. 选择建议

使用 AsyncSubAgent，当：

- 任务耗时较长，父 Agent 不应同步等待。
- 需要独立扩缩容、资源或安全边界。
- 需要后续追加指令、查询和取消。
- 远程 Graph 本身有持久化和部署生命周期。

几秒内能完成、只需一个最终报告的委托，优先声明式或 Compiled 同步 SubAgent，系统会简单很多。

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

## 8. 从零跑通真实流程

真实示例需要两个同时运行的进程：

```text
终端一：LangGraph Agent Server（127.0.0.1:2024）
                         ↑
终端二：run.py 创建父 Agent，并通过 HTTP 启动远程任务
```

### 第一步：进入正确目录

在 PowerShell 中执行：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
```

如果提示符前面是其他项目的环境，例如 `(ai-erp-rag-assistant)`，先退出：

```powershell
deactivate
```

`uv run` 即使发现环境不匹配也会改用当前项目的 `.venv`，但退出旧环境可以避免反复出现 `VIRTUAL_ENV ... does not match` 警告。

### 第二步：安装依赖并确认模型配置

```powershell
uv sync
```

模型环境变量按以下顺序加载：

1. `deep_agent_examples/.env`。
2. 仓库根目录 `LearnOne/.env` 作为回退。

配置按供应商成套选择，不会把 DeepSeek Key 与 `OPENAI_BASE_URL` 混用。使用 DeepSeek 时至少需要：

```text
DEEPSEEK_API_KEY=真实的 API Key
```

未配置 `DEEPSEEK_BASE_URL` 和 `DEEPSEEK_MODEL` 时，项目自动使用：

```text
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

不要把真实 Key 写进 Python、README 或提交到 Git。修改环境配置后必须重启 Agent Server。

### 第三步：终端一启动 Agent Server

Windows 必须在 Python 启动前启用 UTF-8。只把这两个变量写进 `.env` 不能解决 Python 启动阶段的 GBK 解码问题：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
uv run langgraph dev --host 127.0.0.1 --port 2024
```

成功时会看到：

```text
API: http://127.0.0.1:2024
Studio UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
API Docs: http://127.0.0.1:2024/docs
```

显示地址后继续观察几秒。没有出现 worker traceback，并且进程保持运行，才表示服务真正启动成功。这个终端不要关闭，也不要按 `Ctrl+C`。

### 第四步：终端二运行真实示例

在 IDE 中新建第二个终端：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
deactivate
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
uv run python examples\async_subagent\run.py --check-after 5
```

如果 `deactivate` 不存在，忽略这一行即可。

正常输出类似：

```text
task_id: <远程 thread ID>
remote run_id: <远程 run ID>
cached status: running
checked status: running 或 success
parent thread_id: <父 Agent thread ID>
```

`task_id` 可能出现两次：一次来自模型回复，一次由示例脚本明确打印，这是正常现象。

`--check-after 5` 表示等待 5 秒后只检查一次，不会持续轮询。如果结果仍是 `running`，说明后台任务已经成功创建但尚未完成，不是报错。脚本进程退出后，父 Agent 的 `InMemorySaver` 也会消失；生产系统应改用持久化 checkpointer。

### 第五步：验证远程任务状态和结果

从上一步复制 `task_id` 和 `remote run_id`，在新的 PowerShell 中设置：

```powershell
$taskId = "替换为 task_id"
$runId = "替换为 remote run_id"
```

查询 run 状态：

```powershell
Invoke-RestMethod "http://127.0.0.1:2024/threads/$taskId/runs/$runId" |
    Select-Object run_id, status
```

任务完成时 `status` 应为 `success`。如果仍是 `running`，等待十几秒后手动再查一次，不要写无限轮询。

状态变为 `success` 后读取远程 thread 的最终消息：

```powershell
$state = Invoke-RestMethod "http://127.0.0.1:2024/threads/$taskId/state"
$state.values.messages[-1].content
```

预期得到北辰智能硬件供应商风险和 AI 推理服务器库存的中文调查结果。开发服务器使用内存存储，重启终端一后，旧 thread/run 可能不再存在。

## 9. 在 Studio 中验证

1. 保持终端一的 Agent Server 运行。
2. 打开启动日志中的 Studio UI。
3. 确认右上角显示绿色 `Connected`。
4. 在顶部选择 `async_subagent_agent`，不要选 `dynamic_skill_agent`。
5. 点击 `New Thread`。
6. 在 Input 中提交：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "请在后台调查北辰智能硬件和 AI 推理服务器库存，先返回 task_id。"
    }
  ]
}
```

第一次调用应返回 `task_id`，State 的 `async_tasks` 中应出现对应的 `thread_id`、`run_id` 和 `status`。

等待一段时间后，在同一个 Studio thread 中继续提交：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "列出后台任务，并检查刚才任务的当前状态和结果。"
    }
  ]
}
```

必须复用同一个父 thread，因为内置 `check_async_task` 会先从父 State 的 `async_tasks` 查找任务。点击 `New Thread` 会创建新的父 State，不能直接管理旧任务。

## 10. 本次实际遇到的问题

### `VIRTUAL_ENV ... does not match`

原因：终端自动激活了其他项目的虚拟环境。

处理：

```powershell
deactivate
cd D:\PythonProject\LearnOne\deep_agent_examples
```

这是警告，不是导致任务失败的异常。`uv` 提示 `will be ignored` 时已经切换到当前项目环境。

### `UnicodeDecodeError: 'gbk' codec can't decode ...`

原因：Windows 用 GBK 读取 LangGraph 包中的 UTF-8 OpenAPI 文件。错误发生在 Python 启动阶段，项目代码尚未加载 `.env`。

处理：在启动 Agent Server 的同一终端先执行：

```powershell
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
```

然后重新运行 `uv run langgraph dev ...`。

### `httpx.ConnectError` 或连接 `127.0.0.1:2024` 失败

原因：Agent Server 没有启动、启动后 worker 已崩溃，或者 `AGENT_SERVER_URL` 指向了错误地址。

处理：

1. 确认终端一仍在运行且没有 traceback。
2. 浏览器访问 `http://127.0.0.1:2024/docs`。
3. 确认 `AGENT_SERVER_URL=http://127.0.0.1:2024`。

### `OpenAIConnectionError: Connection error`，任务名为 `model`

原因：Agent Server 已连接，但模型 API 无法访问。此前配置还可能把 `DEEPSEEK_API_KEY` 与另一组 `OPENAI_BASE_URL/OPENAI_MODEL` 拼在一起。

当前配置已经改为同一供应商变量成套使用：优先 `LLM_*`，其次 `DEEPSEEK_*`，最后 `OPENAI_*`。检查网络：

```powershell
Test-NetConnection api.deepseek.com -Port 443
```

修改 Key、Base URL 或模型名后，停止并重启 Agent Server。不要把真实 Key 写死到源码。

### `checked status: running`

这不是错误。`--check-after 5` 只在 5 秒后查询一次，远程模型和工具可能需要更长时间。使用第 8 节的 API 命令稍后查询。

### `LangSmith tracing disabled`

这不是错误，只表示没有上传 trace。需要观察 LangSmith 轨迹时配置：

```text
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=真实的 LangSmith Key
LANGSMITH_PROJECT=deep-agent-examples
```

修改后重启 Agent Server。

## 11. 不启动服务器的离线测试

如果只想确认 AsyncSubAgent 的状态逻辑是否正确，不需要模型 Key、Agent Server、LangSmith 或网络：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
uv run python examples\async_subagent\test.py
```

成功时输出：

```text
AsyncSubAgent 离线测试通过
- 启动任务会创建远程 thread/run 并保存跟踪信息
- 查询任务会刷新缓存状态并读取远程结果
- 更新任务会保留 task_id/thread_id 并替换 run_id
- 取消任务会终止当前远程 run 并记录最终状态
```

## 12. LangSmith 中怎样关联父远程两侧

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

## 13. 认证与数据安全

- 托管 LangGraph/LangSmith Deployment 通常通过 SDK 环境变量认证。
- 自托管服务可在 spec `headers` 中提供认证 header，但不要把 token 写进代码或 trace。
- 远程服务必须重新做 tenant、thread、assistant 权限检查；不能因为请求来自父 Agent 就默认可信。
- `task_id` 不是授权凭证。能猜到 ID 不应等于能读取任务。
- 跨租户部署必须隔离 checkpoint、Store、Sandbox、日志和 trace。

## 14. 选择建议

使用 AsyncSubAgent，当：

- 任务耗时较长，父 Agent 不应同步等待。
- 需要独立扩缩容、资源或安全边界。
- 需要后续追加指令、查询和取消。
- 远程 Graph 本身有持久化和部署生命周期。

几秒内能完成、只需一个最终报告的委托，优先声明式或 Compiled 同步 SubAgent，系统会简单很多。

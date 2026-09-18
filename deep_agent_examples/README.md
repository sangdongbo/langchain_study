# Deep Agents 可运行示例

这个目录把 Deep Agents 文档中的关键概念做成可启动的小示例。所有业务工具都使用内存 mock 数据，不连接 ERP、数据库或向量库。

运行方式有两种：

- `langgraph dev`：在 LangGraph Studio 中选择 graph、查看状态、工具调用、子 Agent 和 HITL 中断。
- `deep-agent-example`：从终端运行，并把相同轨迹发送到 LangSmith。

## 1. 示例清单

| Graph / CLI 名称 | 展示内容 | 启动条件 |
| --- | --- | --- |
| `tool_agent` / `tool` | 多工具调用轨迹 | 模型 Key |
| `lifecycle_agent` / `lifecycle` | 普通 Agent hook、工具循环与 State | 模型 Key |
| `subagent_lifecycle_agent` / `subagent-lifecycle` | 父/子 Agent 生命周期与嵌套 trace | 模型 Key |
| `subagent_agent` / `subagent` | 声明式 `SubAgent` | 模型 Key |
| `compiled_subagent_agent` / `compiled` | 复用预编译 LangChain Agent | 模型 Key |
| `remote_research_agent` / `remote` | Async 示例的远程执行目标 | 模型 Key |
| `async_subagent_agent` / `async` | Agent Protocol 后台任务 | 本地 Agent Server 已启动 |
| `backend_agent` / `backend` | `StateBackend` 文件写入 | 模型 Key |
| `dynamic_skill_agent` / `skill` | 调用时注入 State Skill | 模型 Key；输入包含 `files` |
| `hitl_harness_agent` / `hitl` | 权限、调用预算、HITL、恢复 | Studio 或 CLI `--approve` |
| `local_shell_agent` / `local-shell` | 本地 shell 与执行审批 | 仅可信本机开发 |
| CLI `langsmith-sandbox` | LangSmith 云沙箱 | 账号已开通 Sandbox |

`OpenSandbox` 在 `optional_opensandbox/` 中单独运行，因为目前唯一的 `langchain-opensandbox 0.1.0` 明确要求 `deepagents >=0.6.12,<0.7`，不能装进本项目的 `deepagents 0.7.x` 环境。

普通 Agent、同步子 Agent、`CompiledSubAgent` 与 `AsyncSubAgent` 的创建、执行、checkpoint、interrupt 和结束语义见 [LIFECYCLE.md](LIFECYCLE.md)。

固定目录 Skill、基于 `StateBackend.files` 的动态 Skill、metadata 缓存、可信路由和权限边界见 [DYNAMIC_SKILLS.md](DYNAMIC_SKILLS.md)。

三种子 Agent 已分成独立专题和独立代码：

- [声明式 SubAgent：isolated、fork 与 State 传播](DECLARATIVE_SUBAGENT.md)
- [CompiledSubAgent：复用现成 Agent 与 StateGraph](COMPILED_SUBAGENT.md)
- [AsyncSubAgent：远程 thread、run 与后台任务状态机](ASYNC_SUBAGENT.md)

## 2. 安装和配置

```powershell
cd deep_agent_examples
Copy-Item .env.example .env
uv sync
```

编辑 `.env`，至少配置模型：

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

要把轨迹发送到 LangSmith，再配置：

```text
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_xxx
LANGSMITH_PROJECT=deep-agent-examples
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

不要提交真实 `.env`。

Windows 系统区域不是 UTF-8 时，`PYTHONUTF8=1` 也是 LangGraph API 子进程正确读取 OpenAPI 文件所必需的；否则可能在 graph 加载前出现 GBK 解码错误。

## 3. 在 Studio 中启动

```powershell
uv run langgraph dev --host 127.0.0.1 --port 2024
```

`langgraph.json` 会注册 11 个 graph。浏览器中的 Studio 用于操作本地 Agent Server；配置 `LANGSMITH_TRACING=true` 后，模型、工具和子 Agent 轨迹还会出现在 LangSmith 的 `deep-agent-examples` 项目中。

普通输入：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件，请评审。"
    }
  ]
}
```

### Dynamic Skill 输入

`dynamic_skill_agent` 使用 `StateBackend`，所以 Skill 要作为该 thread 的 `files` 输入。这里的动态是“调用方为新 thread 决定有哪些 Skill 文件”，不是框架按角色自动增删工具：

```json
{
  "messages": [
    {
      "role": "user",
      "content": "按本会话技能评审研发平台部采购 4 台 AI 推理服务器，单价 68000 元，供应商北辰智能硬件。"
    }
  ],
  "files": {
    "/skills/session/procurement-review/SKILL.md": {
      "content": "---\nname: procurement-review\ndescription: Review purchases with deterministic evidence\n---\n\n# Procedure\n1. Calculate total with the tool.\n2. Check inventory, budget and supplier.\n3. Answer in Chinese with evidence and recommendation.\n",
      "encoding": "utf-8"
    }
  }
}
```

真实执行顺序是：`files` 进入 State → `SkillsMiddleware.before_agent` 扫描 frontmatter → metadata 进入 system prompt → 模型调用 `read_file` 读取完整正文 → 按 Skill 调用业务工具。固定目录 Skill 和 State Skill 都使用这种 progressive disclosure，不会默认把全部正文塞进 prompt。

同一 checkpointed thread 会缓存 `skills_metadata`，即使首次结果为空也不会自动重扫。更换 Skill 集合时新建 thread。Skill 只是说明书；`allowed-tools` 也不是强制 ACL，实际权限必须由工具、Middleware、HITL 和 Sandbox 实施。完整机制与排错表见 [DYNAMIC_SKILLS.md](DYNAMIC_SKILLS.md)。

对应的可执行 Python 文件：

```powershell
# 真实模型；LANGSMITH_TRACING=true 时上传 trace
uv run python examples/dynamic_skills.py
uv run python examples/dynamic_skills.py --role risk-reviewer --task-type supplier-risk

# Fake Model 确定性测试；不需要 Key，也不上传 trace
uv run python examples/test_dynamic_skills.py
```

### AsyncSubAgent 输入

先保持同一个 `langgraph dev` 服务运行，确认 `.env` 中：

```text
AGENT_SERVER_URL=http://127.0.0.1:2024
```

然后在 Studio 选择 `async_subagent_agent`：

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

它会通过 Agent Protocol 调用同一服务中的 `remote_research_agent`。之后可让它调用 `list_async_tasks` 或 `check_async_task`。不要持续轮询。

### HITL

`hitl_harness_agent` 的 `publish_review` 和 `/reports/final/**` 写入会产生 interrupt。Studio 会显示待审批动作，可以批准、修改、拒绝或代答。Server 管理 checkpoint，因此 Studio 导出的 graph 没有内置 `InMemorySaver`。

## 4. 从命令行运行

```powershell
uv run deep-agent-example tool
uv run deep-agent-example lifecycle --thread-id lifecycle-001
uv run deep-agent-example subagent-lifecycle --thread-id subagent-lifecycle-001
uv run deep-agent-example subagent
uv run deep-agent-example compiled
uv run deep-agent-example backend
uv run deep-agent-example skill
uv run deep-agent-example hitl --approve --thread-id hitl-001
```

AsyncSubAgent 的 CLI 同样要求本地 Agent Server 已经启动：

```powershell
uv run deep-agent-example async --thread-id async-001
```

每次 CLI 调用都会添加 `deep-agent-example` 和示例名 tag，并写入 example metadata，便于在 LangSmith 过滤。

生命周期也提供独立 Python 文件和无 Key 测试：

```powershell
# 真实模型；LANGSMITH_TRACING=true 时上传 trace
uv run python examples/agent_lifecycle.py --kind agent
uv run python examples/agent_lifecycle.py --kind subagent

# Fake Model；同时验证 invoke 与 ainvoke
uv run python examples/test_lifecycle.py
```

三种子 Agent 分开运行：

```powershell
# 声明式 SubAgent：真实模型与 LangSmith
uv run python examples/declarative_subagent.py --mode isolated
uv run python examples/declarative_subagent.py --mode fork

# CompiledSubAgent：真实模型与 LangSmith
uv run python examples/compiled_subagent.py

# AsyncSubAgent：先启动 langgraph dev，再运行
uv run python examples/async_subagent.py
uv run python examples/async_subagent.py --check-after 5
```

对应的无 Key、无网络确定性测试：

```powershell
uv run python examples/test_declarative_subagent.py
uv run python examples/test_compiled_subagent.py
uv run python examples/test_async_subagent.py
```

## 5. 本地 shell 不是沙箱

`local_shell_agent` 使用 `LocalShellBackend`，只用于展示 `execute` 和 HITL。它具有当前用户的主机权限：

- `virtual_mode=True` 只约束文件工具路径，约束不了 shell。
- 环境变量只传入 `PATH` 等最小集合，但这不是进程隔离。
- 示例提示词要求写入 `workspace/artifacts/`；写入、编辑、删除和执行都必须逐次审批。
- `deepagents 0.7.x` 不允许把 `FilesystemPermission` 与执行型 backend 组合，因为 shell 可以绕过文件工具的路径规则；本例没有声称 HITL 能替代沙箱。
- 不要把它放进 Web API、多租户系统或不可信输入前面。

运行：

```powershell
uv run deep-agent-example local-shell --approve --thread-id local-001
```

## 6. LangSmith 云沙箱

账号开通 LangSmith Sandbox 后运行：

```powershell
uv run deep-agent-example langsmith-sandbox
```

脚本为一次运行创建临时 sandbox，并在退出上下文时自动删除。可通过 `LANGSMITH_SANDBOX_SNAPSHOT` 指定已有 snapshot。Sandbox 是否可用取决于 LangSmith 账号、区域和当前 beta 权限，不是 tracing API Key 本身就一定具备。

## 7. OpenSandbox 独立环境

先启动自托管 OpenSandbox Server，再创建独立虚拟环境。不要把依赖装进主示例环境：

```powershell
cd optional_opensandbox
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

该脚本仍会读取上一级 `.env`，因此模型轨迹可以进入同一个 LangSmith 项目。兼容适配包发布 `deepagents 0.7+` 版本后，再考虑合并环境。

## 8. 静态自检

这个检查不会调用模型、数据库、Sandbox 或 Agent Server：

```powershell
uv run python scripts_smoke.py
uv run python examples/test_dynamic_skills.py
uv run python examples/test_lifecycle.py
uv run python examples/test_declarative_subagent.py
uv run python examples/test_compiled_subagent.py
uv run python examples/test_async_subagent.py
```

第一条验证 11 个 graph 都可导入、`langgraph.json` 注册一致、mock 工具结果正确、生命周期 reducer 和动态 Skill 文件存在。其余脚本使用 Fake Model、编译后的 StateGraph 或 Fake Agent Protocol client，分别验证 Dynamic Skills、生命周期、声明式、Compiled 和 Async SubAgent，不调用真实模型或 LangSmith。

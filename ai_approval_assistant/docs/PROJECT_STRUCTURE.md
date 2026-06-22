# AI Approval Assistant Project Structure

本文说明 `ai_approval_assistant` 的目录职责、启动方式，以及一次请求从前端接口进入 LangGraph 工作流的完整流程。

## 目录结构

```text
ai_approval_assistant/
├── app/
│   ├── agents/
│   │   ├── approval/
│   │   ├── approval_agent.py
│   │   └── user_profile_agent.py
│   ├── api/
│   │   ├── chat.py
│   │   └── health.py
│   ├── graph/
│   │   ├── approval_workflow.py
│   │   ├── state.py
│   │   └── studio.py
│   ├── mock_data/
│   ├── schemas/
│   ├── services/
│   ├── tools/
│   ├── logging_config.py
│   ├── main.py
│   └── middleware.py
├── docs/
├── logs/
├── prompts/
├── scripts/
├── tests/
├── .env
├── .env.example
├── langgraph.json
├── pyproject.toml
├── start_windows.ps1
├── stop_windows.ps1
└── uv.lock
```

## 目录职责

### `app/`

应用主代码目录。

### `app/main.py`

FastAPI 应用入口。启动时会：

1. 加载 `.env` 配置。
2. 初始化日志。
3. 注册请求日志中间件。
4. 注册健康检查接口和聊天接口。

### `app/api/`

HTTP API 层。

- `health.py`：提供 `GET /health`。
- `chat.py`：提供 `POST /api/ai-approval/chat`。

`chat.py` 会兼容两种凭证传入方式：

- 请求体里的 `authorization` / `uid`
- 请求头里的 `Authorization` / `UID`

最终会调用 `chat_application_service.run_turn()` 进入应用服务层。

### `app/graph/`

LangGraph 入口和共享状态定义。

- `state.py`：定义 `ApprovalAgentState` / `ApprovalState`，也就是所有 agent 共享的状态。
- `approval_workflow.py`：正式 graph 编排入口，负责 `create_workflow`，并保留旧 `run_chat_turn` 兼容入口。
- `studio.py`：LangGraph Studio 使用的 graph 入口，`langgraph.json` 指向这里。

### `app/agents/`

Agent 节点和业务流程。

- `approval_agent.py`：核心业务节点文件，包含审批创建 agent、用户信息 agent、通用聊天 agent、记忆节点和意图路由节点。
- `approval/`：审批流程拆出来的辅助模块，比如审批人选择、字段输入、消息构造、路由判断、提交参数等。
- `user_profile_agent.py`：旧的用户资料加载模块，目前不再作为顶层 graph 节点使用。

当前正式 graph 结构是：

```text
memory_agent
-> intent_router
   -> approval_creation_agent
   -> user_info_agent
   -> general_chat
```

`approval_creation_agent` 内部会继续执行审批创建状态机：

```text
load_context
-> classify
-> decision_review
-> collect
-> validate
-> assignee
-> preview
-> submit
```

这些内部步骤不会在 Studio graph 里展开，但会写入 `trace`，方便排查。

### `app/schemas/`

Pydantic 数据模型。

- 聊天请求/响应模型。
- 审批模板、审批字段、审批节点、审批人等业务模型。
- ERP/CRM 调用时使用的 `UserContext`。

### `app/services/`

外部系统和基础能力封装。

常见职责包括：

- 聊天应用服务编排。
- 调 ERP/CRM 接口。
- 用户信息查询。
- 会话状态保存。
- 短期记忆。
- 模型服务调用。
- debug 日志写入。
- 审批 payload 构造和模板缓存。

其中 `chat_application_service.py` 是 API 到 graph 之间的应用服务层。它负责：

1. 写入请求 debug log。
2. 加载会话状态。
3. 处理本地模拟审批状态到真实 ERP 凭证的切换。
4. 将请求字段写入 `AgentState`。
5. 调用 `create_workflow().invoke(state)`。
6. 将 graph state 转换成 `ChatResponse`。
7. 保存会话状态。
8. 写入响应 debug log。

### `app/tools/`

LangChain/LangGraph tool 定义。

例如：

- 查询当前用户信息。
- 查询直属上级信息。
- 搜索审批模板。
- 查询审批表单字段。
- 查询动态选项。

### `app/mock_data/`

本地模拟数据。没有真实 ERP 凭证时，审批模板和用户上下文可以走这里，方便本地开发。

### `prompts/`

LLM prompt 配置和模板。

### `tests/`

自动化测试目录。主要覆盖：

- FastAPI 聊天接口。
- Graph 结构。
- 用户信息工具。
- CRM 服务适配。
- 会话状态。
- 审批 payload 构造。

### `logs/`

运行日志目录。

启动 LangGraph Studio 后，默认会写入：

```text
logs/studio.out.log
logs/studio.err.log
```

### `.env` / `.env.example`

环境变量配置。

常用配置：

```text
AI_APPROVAL_CRM_BASE_URL=https://dev3.lanerp.com/
AI_APPROVAL_SESSION_BACKEND=redis
AI_APPROVAL_STUDIO_ENABLED=false
AI_APPROVAL_STUDIO_PORT=2024
AI_APPROVAL_KILL_EXISTING_PORT_PROCESS=false
```

### `langgraph.json`

LangGraph Studio 配置文件。

当前配置：

```json
{
  "dependencies": ["."],
  "graphs": {
    "approval_assistant": "app.graph.studio:graph"
  },
  "env": ".env"
}
```

Studio 会从 `app.graph.studio:graph` 加载 graph。

### `start_windows.ps1`

Windows 一键启动脚本。

职责：

1. 进入项目目录。
2. 读取 `.env`。
3. 检查 `uv` 是否可用。
4. 执行 `uv sync --dev` 同步依赖，除非传入 `-SkipSync`。
5. 按需启动 LangGraph Studio。
6. 检查或清理 API 端口。
7. 启动 FastAPI 服务。

### `stop_windows.ps1`

Windows 停止脚本。

职责：

1. 读取 `.env`。
2. 如果启用了 Studio，则停止 Studio 端口。
3. 停止 FastAPI 服务端口。
4. 支持 `-DryRun` 只查看将要停止的进程。

## 启动方式

### 1. 进入项目目录

```powershell
cd D:\PythonProject\LearnOne\ai_approval_assistant
```

### 2. 准备 `.env`

如果还没有 `.env`，可以基于 `.env.example` 创建。

关键项：

```text
AI_APPROVAL_CRM_BASE_URL=https://dev3.lanerp.com/
AI_APPROVAL_SESSION_BACKEND=redis
REDIS_HOST=127.0.0.1
AI_APPROVAL_STUDIO_ENABLED=true
AI_APPROVAL_STUDIO_PORT=2024
```

本地只调试 API，也可以关闭 Studio：

```text
AI_APPROVAL_STUDIO_ENABLED=false
```

### 3. 启动服务

```powershell
.\start_windows.ps1
```

默认行为：

- API 地址：`http://127.0.0.1:8010`
- 如果 `.env` 中 `AI_APPROVAL_STUDIO_ENABLED=true`，同时启动 Studio：`http://127.0.0.1:2024`
- 默认启用 uvicorn reload。
- 默认会先执行 `uv sync --dev`。

### 4. 常用启动参数

跳过依赖同步：

```powershell
.\start_windows.ps1 -SkipSync
```

不启动 Studio：

```powershell
.\start_windows.ps1 -NoStudio
```

关闭 reload：

```powershell
.\start_windows.ps1 -NoReload
```

换端口启动 API：

```powershell
.\start_windows.ps1 -Port 8020
```

### 5. 停止服务

```powershell
.\stop_windows.ps1
```

只查看会停止哪些进程：

```powershell
.\stop_windows.ps1 -DryRun
```

不停止 Studio，只停止 API：

```powershell
.\stop_windows.ps1 -NoStudio
```

## 启动脚本完整流程

执行：

```powershell
.\start_windows.ps1
```

内部流程：

```text
start_windows.ps1
-> Set-Location 到 ai_approval_assistant
-> 读取 .env
-> 检查 uv
-> 设置 UV_LINK_MODE=copy
-> 如果没有 AI_APPROVAL_CRM_BASE_URL，则默认 https://dev3.lanerp.com
-> 执行 uv sync --dev
-> 定位 .venv\Scripts\python.exe
-> 如果 AI_APPROVAL_STUDIO_ENABLED=true：
   -> 定位 .venv\Scripts\langgraph.exe
   -> 启动 langgraph dev --host 127.0.0.1 --port 2024 --no-browser
   -> Studio 日志写入 logs/studio.out.log 和 logs/studio.err.log
-> 检查 API 端口 8010
-> 启动 uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

## 请求处理完整流程

前端调用：

```http
POST /api/ai-approval/chat
```

请求体示例：

```json
{
  "session_id": "approval-assistant-session",
  "user_id": "863",
  "uid": "863",
  "authorization": "Bearer token",
  "message": "我的用户上级是？"
}
```

后端处理流程：

```text
FastAPI app.main
-> app.api.chat.chat()
-> 补齐请求头里的 Authorization / UID
-> chat_application_service.run_turn()
-> session_state_service.load()
-> 写入本轮 user_id / uid / authorization / user_message
-> create_workflow()
-> graph.invoke(state)
-> memory_agent
-> intent_router
   -> user_info_agent
   -> approval_creation_agent
   -> general_chat
-> 生成 ChatResponse
-> append_assistant_message()
-> session_state_service.save()
-> 返回接口响应
```

## 三类 agent 职责

### `memory_agent`

记录本轮用户输入到短期记忆，供后续回复参考。

### `intent_router`

判断本轮消息应该交给哪个业务 agent：

- 用户资料问题：`user_info_agent`
- 审批创建/继续审批：`approval_creation_agent`
- 普通聊天：`general_chat`

### `user_info_agent`

处理当前用户、部门、直属上级等问题。

它会：

1. 优先复用 `AgentState.user_profile` 和 `AgentState.superior_profile`。
2. 缺失时调用用户 tools 查询。
3. 把查询结果写回 `AgentState`。
4. 组织用户可读回答。

### `approval_creation_agent`

处理审批发起、字段收集、审批人选择、预览和提交。

正式 graph 中它是一个业务 agent 节点，内部步骤通过代码状态机执行，并写入 `trace`。

### `general_chat`

处理普通问答。如果当前存在未完成审批，会在回答后提示继续当前审批。

## Studio 查看方式

如果 `.env` 中开启：

```text
AI_APPROVAL_STUDIO_ENABLED=true
```

启动后访问：

```text
http://127.0.0.1:2024
```

Studio 加载入口：

```text
app.graph.studio:graph
```

正式生产 graph 只展示业务级节点，不展开审批内部状态机。内部步骤可以通过响应里的 `trace` 或日志排查。

## 健康检查

```http
GET /health
```

返回：

```json
{
  "status": "ok"
}
```

## 常见问题

### 端口被占用

如果 8010 或 2024 被占用，可以：

1. 执行停止脚本：

```powershell
.\stop_windows.ps1
```

2. 或在 `.env` 设置：

```text
AI_APPROVAL_KILL_EXISTING_PORT_PROCESS=true
```

### 修改代码后 Studio 没变化

重启 Studio：

```powershell
.\stop_windows.ps1
.\start_windows.ps1 -SkipSync
```

### 不想每次同步依赖

```powershell
.\start_windows.ps1 -SkipSync
```

### 只启动 API，不启动 Studio

```powershell
.\start_windows.ps1 -NoStudio
```

# AI Approval Assistant

接口版 AI 办公助手，当前以“审批发起 + 用户信息查询 + 写日志/日报”为核心场景。

当前目录是独立后端骨架，只参考 `docs/ai_approval` 中的方案，不依赖仓库里的其他 demo 目录。当前实现同时支持本地 mock CRM 演示和真实 ERP 接口调用；审批真实接入的主要边界在 `app/services/crm_service.py`，日报真实接入的主要边界在 `app/services/daily_report_service.py`。

## 1. 功能范围

- `GET /health`：健康检查。
- `POST /api/ai-approval/chat`：聊天审批主接口。
- 按 `session_id` 保存多轮审批会话状态。
- `GET/POST /api/ai-approval/time-travel/...`：查看、恢复和分叉会话 checkpoint，用于学习 LangGraph 的时光回溯思想。
- 从 mock CRM 或真实 ERP 获取当前用户可发起的审批模板。
- 远程模式下，普通问候和帮助问句走通用聊天，不会误触发审批模板搜索。
- 明确审批意图时按关键词调用 `/api/approval/list` 搜索模板。
- 多个模板命中时返回结构化单选控件，让前端选择模板。
- 按审批模板动态收集字段。
- 快速发起只收集必填字段，非必填字段默认忽略。
- 支持结构化控件返回和接收：单选、人员选择、日期时间、日期、文本、多行文本、地址。
- 缺字段时在聊天里逐项追问。
- 字段完整后调用 CRM 预校验。
- 真实 ERP 模板会调用 `/api/field/formFields` 获取字段，调用 `/api/approval/getNodes` 获取审批流程节点。
- 需要发起人选择办理人/审批人时，返回 `user_select` 控件。
- 生成审批预览。
- 用户明确回复“确认提交”后才创建审批。
- 支持取消、修改和确认提交守卫。
- 支持有界决策复核 `decision_review`，避免无限反复思考。
- 支持轻量时光回溯：每轮聊天后记录一份内存 checkpoint，可查看历史状态、恢复当前会话或从历史点分叉新会话。
- 支持写日志/日报意图路由，顶层 graph 中与审批、用户信息、普通聊天并列。
- `daily_report_form_agent` 会加载日报表单字段、日报配置、草稿和同步数据，并返回 `ui_action.open_daily_report_form` 给前端弹正常写日志表单。
- 前端填写完整日报 payload 后，agent 生成预览；用户明确回复“确认提交”后调用 `/oa/dailyReport/add` 提交。
- `daily_report_chat_agent` 支持简单快捷日报：用用户消息作为 `content` 生成预览，确认后提交；复杂自定义字段仍建议走表单版。

当前 mock 审批模板库已经模拟“分类 + 常用审批 + 多模板”的形态，包含：

- 请假申请
- 报销申请
- 采购申请
- 用章申请
- 测试入库
- 测试出库
- 测试加班

## 2. 技术栈

- Python 3.14：当前项目运行环境。
- FastAPI：HTTP API 服务。
- Uvicorn：ASGI 服务启动器。
- Pydantic：请求、响应、审批模板和 CRM 数据结构。
- LangGraph：多 Agent 会话流程编排。
- DeepSeek Chat：可选 LLM，用于审批类型识别、字段抽取和决策复核。
- Python logging：请求日志和后续业务日志基础设施。
- pytest：接口测试。
- httpx / FastAPI TestClient：接口测试客户端。

当前已接入可选 DeepSeek LLM。默认不启用真实模型请求；设置 `AI_APPROVAL_USE_LLM=true` 并配置 `DEEPSEEK_API_KEY` 后，会在审批类型识别、字段抽取和 `decision_review` 复核中调用 DeepSeek。规则抽取、CRM 预校验和提交守卫仍保留作为兜底。

## 3. 目录结构

```text
ai_approval_assistant/
├── app/
│   ├── api/
│   │   ├── chat.py
│   │   └── health.py
│   ├── graph/
│   │   ├── extractors.py
│   │   ├── state.py
│   │   └── workflow.py
│   ├── agents/
│   │   ├── approval_agent.py
│   │   ├── daily_report_form_agent.py
│   │   ├── daily_report_chat_agent.py
│   │   └── user_profile_agent.py
│   ├── mock_data/
│   │   └── approval_templates.py
│   ├── schemas/
│   │   ├── approval.py
│   │   ├── daily_report.py
│   │   └── chat.py
│   ├── services/
│   │   ├── crm_service.py
│   │   ├── daily_report_api_client.py
│   │   ├── daily_report_service.py
│   │   ├── model_service.py
│   │   ├── prompt_config_service.py
│   │   └── session_state_service.py
│   └── main.py
├── docs/
│   ├── README.md
│   └── session_flow.mmd
├── prompts/
│   └── approval_prompts.json
├── scripts/
│   └── export_graph.py
└── tests/
    └── test_chat_api.py
```

## 4. 启动服务

推荐把 `ai_approval_assistant` 当成独立项目目录执行：

```bash
cd ai_approval_assistant
.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

启动成功后会看到类似输出：

```text
Uvicorn running on http://127.0.0.1:8010
```

如果使用 `uv`：

```bash
uv run uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

Windows PowerShell 推荐把 `ai_approval_assistant` 当成独立项目目录执行：

```powershell
.\start_windows.ps1
```

也可以直接运行 bat 包装器：

```bat
start_windows.bat
```

脚本会先在 `ai_approval_assistant` 内执行 `uv sync --dev` 安装/同步本项目 `pyproject.toml` 里声明的依赖，然后用 `.venv\Scripts\python.exe` 启动服务。环境变量放在 `.env`，可参考 `.env.example`。默认地址仍然是：

```text
http://127.0.0.1:8010
```

如果要同一个脚本同时启动 LangGraph Studio，在 `.env` 中开启：

```text
AI_APPROVAL_STUDIO_ENABLED=true
AI_APPROVAL_STUDIO_HOST=127.0.0.1
AI_APPROVAL_STUDIO_PORT=2024
```

然后仍然运行：

```powershell
.\start_windows.ps1
```

脚本会后台启动 Studio，本窗口继续前台运行 FastAPI。临时不启动 Studio 可以加：

```powershell
.\start_windows.ps1 -NoStudio
```

如果端口已被上一次启动的进程占用，可以在 `.env` 开启自动清理：

```text
AI_APPROVAL_KILL_EXISTING_PORT_PROCESS=true
```

脚本会在启动前停止占用 FastAPI 端口和 Studio 端口的监听进程。

如需修改端口：

```powershell
.\start_windows.ps1 -Port 8011
```

如果依赖已经安装好，只想直接启动：

```powershell
.\start_windows.ps1 -SkipSync
```

启用 DeepSeek：

```bash
export AI_APPROVAL_USE_LLM=true
export DEEPSEEK_API_KEY=your_deepseek_api_key_here
export DEEPSEEK_MODEL=deepseek-chat
export DEEPSEEK_TEMPERATURE=0

.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010 --reload
```

不设置 `AI_APPROVAL_USE_LLM=true` 时，服务不会请求模型，会使用规则版抽取和复核。

### 4.1 配置 Prompt

默认 prompt 文件：

```text
prompts/approval_prompts.json
```

现在 prompt 不写死在代码里，配置文件里分成三段：

| 配置段 | 用途 |
|---|---|
| `classification` | 审批模板识别，从候选模板中选出当前审批 |
| `slot_extraction` | 审批字段抽取，按当前模板收集字段 |
| `decision_review` | 路由安全复核，防止误提交或不明确确认 |

每段都有：

| 字段 | 说明 |
|---|---|
| `system` | 发给模型的 system prompt |
| `output_schema` | 要求模型返回的 JSON 结构 |
| `rules` | 当前任务的规则、约束和调试重点 |

`decision_review` 额外有 `allowed_routes`，用于限制模型只能返回：

```json
["collect", "submit", "cancel", "clarify"]
```

如果你想调试一版 prompt，不建议直接改默认文件。可以复制一份：

```bash
cp prompts/approval_prompts.json /tmp/approval_prompts.debug.json
```

然后启动时指定：

```bash
export AI_APPROVAL_PROMPT_FILE=/tmp/approval_prompts.debug.json
export AI_APPROVAL_USE_LLM=true
export DEEPSEEK_API_KEY=your_deepseek_api_key_here

.venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8010
```

注意：prompt 文件只在服务进程内加载并缓存。修改 JSON 后，需要重启服务才能生效。

## 5. 停止服务

如果服务在当前终端前台运行，按：

```text
Ctrl + C
```

如果忘了服务在哪个终端，可以查看端口：

```bash
lsof -i :8010
```

然后停止对应进程：

```bash
kill <PID>
```

## 6. API 文档

服务启动后打开：

```text
http://127.0.0.1:8010/docs
```

这里是 FastAPI 自动生成的 Swagger 页面，可以直接调试接口。

## 7. 接口说明

### 7.1 健康检查

```http
GET /health
```

请求：

```bash
curl -s http://127.0.0.1:8010/health
```

响应：

```json
{
  "status": "ok"
}
```

### 7.2 聊天审批主接口

```http
POST /api/ai-approval/chat
```

请求字段：

```json
{
  "session_id": "S001",
  "user_id": "U001",
  "uid": "863",
  "authorization": "Bearer your_token_here",
  "message": "我要报销餐饮费 2000 元，客户招待，发票已提供",
  "answer": null
}
```

字段说明：

| 字段 | 说明 |
|---|---|
| `session_id` | 会话 ID，同一轮审批流程必须保持一致 |
| `user_id` | 当前用户 ID，mock 数据里可用 `U001` |
| `uid` | 可选，真实 ERP 用户 UID；传入后会作为 `UID` 请求头调用审批列表接口 |
| `authorization` | 可选，真实 ERP 登录凭证；传入后会作为 `Authorization` 请求头调用审批列表接口 |
| `message` | 用户本轮聊天内容 |
| `answer` | 可选，前端结构化控件的回传值；普通文本聊天传 `null` 或省略 |

传入 `uid` 和 `authorization` 后，后端会按消息意图决定是否调用真实 ERP：

- 普通问候、帮助问句，例如 `你好`、`怎么新增审批`：直接走通用聊天，不调用模板搜索。
- 明确审批意图或模板关键词，例如 `我要请假`、`我要外出`、`测试外出`：调用审批列表接口搜索模板。

```text
${AI_APPROVAL_CRM_BASE_URL}/api/approval/list
```

识别到具体审批模板后，会再调用字段接口获取当前模板字段：

```text
${AI_APPROVAL_CRM_BASE_URL}/api/field/formFields
```

字段接口请求体示例：

```json
{
  "field_form": "approval_type_5911"
}
```

如果需要切换地址，可以通过环境变量覆盖：

```text
AI_APPROVAL_CRM_BASE_URL=http://localhost:8002
```

推荐写入 `.env`：

```text
AI_APPROVAL_CRM_BASE_URL=http://localhost:8002
```

如某个接口需要单独覆盖，也仍然兼容以下环境变量：

```text
AI_APPROVAL_LIST_URL=http://localhost:8002/api/approval/list
AI_APPROVAL_FORM_FIELDS_URL=http://localhost:8002/api/field/formFields
AI_APPROVAL_GET_NODES_URL=http://localhost:8002/api/approval/getNodes
AI_APPROVAL_ADD_URL=http://localhost:8002/api/approval/add
```

远程模板和字段详情会短时间缓存，减少同一会话反复调用 `/api/approval/list` 和 `/api/field/formFields`。默认 TTL 是 300 秒，模板更新后最迟会在 TTL 到期后重新拉取：

```text
AI_APPROVAL_TEMPLATE_CACHE_TTL_SECONDS=300
```

动态下拉也会按用户和请求参数短时间缓存，例如请假类型 `/api/attendance/getHolidayRuleByUser`、关联订单 `/api/Company/getRelatedList`。默认 TTL 是 300 秒：

```text
AI_APPROVAL_DYNAMIC_OPTIONS_CACHE_TTL_SECONDS=300
```

设置为 0 可以关闭动态下拉缓存：

```text
AI_APPROVAL_DYNAMIC_OPTIONS_CACHE_TTL_SECONDS=0
```

如果调试模板配置或希望每次都实时读取，可以设置为 0 禁用缓存：

```text
AI_APPROVAL_TEMPLATE_CACHE_TTL_SECONDS=0
```

会话状态默认支持 Redis 持久化，服务重启或多实例部署时可以继续审批中间状态：

```text
AI_APPROVAL_SESSION_BACKEND=redis
AI_APPROVAL_SESSION_TTL_SECONDS=7200
REDIS_HOST=127.0.0.1
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_DB=0
REDIS_PROTOCOL=2
REDIS_PREFIX=lanerp20_local_
```

如果本地没有 Redis，或需要纯内存演示：

```text
AI_APPROVAL_SESSION_BACKEND=memory
```

响应核心字段：

| 字段 | 说明 |
|---|---|
| `status` | 当前流程状态 |
| `assistant_message` | 返回给用户看的文本 |
| `approval_type` | 当前匹配到的审批类型 |
| `collected_slots` | 已收集字段 |
| `collected_values` | 已收集字段的结构化原始值，用于提交 ERP |
| `missing_fields` | 当前缺失字段 |
| `awaiting_field` | 正在等待用户补充的字段 |
| `awaiting_field_key` | 当前等待字段的机器 key |
| `awaiting_field_label` | 当前等待字段的展示名称 |
| `awaiting_input` | 当前前端可直接渲染的控件描述 |
| `preview` | 审批预览 |
| `actions` | 当前可执行动作 |
| `request_id` | 提交成功后的申请编号 |
| `idempotency_key` | 提交幂等键，用于防重复提交 |
| `field_errors` | 字段级校验错误 |
| `trace` | 本轮 LangGraph 节点路径 |

状态说明：

| 状态 | 含义 |
|---|---|
| `idle` | 空闲或还没有进入审批流程 |
| `collecting` | 正在收集审批字段 |
| `awaiting_assignee_selection` | 字段完整，等待选择审批流程中的办理人/审批人 |
| `awaiting_confirmation` | 字段完整，等待用户确认提交 |
| `submitted` | 已提交审批 |
| `cancelled` | 已取消 |
| `error` | 出错 |

### 7.3 `awaiting_input` 和 `answer` 约定

当后端需要前端渲染结构化控件时，会返回 `awaiting_input`。前端展示该控件，用户选择或填写后，把结果放到下一轮请求的 `answer` 中。

`awaiting_input` 通用结构：

```json
{
  "field_key": "rest_holiday_rule_id",
  "label": "请假类型",
  "type": "single_select",
  "required": true,
  "placeholder": "请选择请假类型",
  "options": [
    { "label": "调休假（余8小时）", "value": 11 }
  ],
  "multiple": null,
  "min": null,
  "max": null,
  "value_schema": null
}
```

支持的 `type`：

| type | 用途 |
|---|---|
| `single_select` | 普通单选，例如审批模板、请假类型 |
| `user_select` | 人员选择，例如办理人/审批人 |
| `datetime` | 日期时间 |
| `date` | 日期 |
| `text` | 单行文本 |
| `textarea` | 多行文本 |
| `address` | 地址，`value_schema` 为 `{ "area": "array", "detail": "string" }` |

前端回传 `answer` 示例：

```json
{
  "field_key": "rest_holiday_rule_id",
  "type": "single_select",
  "label": "调休假（余8小时）",
  "value": 11
}
```

审批模板选择：

```json
{
  "field_key": "__approval_template__",
  "type": "single_select",
  "label": "测试外出",
  "value": "remote_5911"
}
```

办理人/审批人选择：

```json
{
  "field_key": "__approval_assignee__:12204",
  "type": "user_select",
  "label": "张三",
  "value": "864"
}
```

日期时间：

```json
{
  "field_key": "rest_start_time",
  "type": "datetime",
  "label": "2026-06-13 09:00",
  "value": "2026-06-13 09:00:00"
}
```

地址：

```json
{
  "field_key": "go_out_addr",
  "type": "address",
  "label": "上海市浦东新区张江路 88 号",
  "value": {
    "area": ["上海市", "浦东新区"],
    "detail": "张江路 88 号"
  }
}
```

前端建议只根据 `awaiting_input` 渲染控件，不要解析 `assistant_message`。当 `awaiting_input.options` 为空时，应给出“暂无可选项/请稍后重试”的提示。

### 7.4 审批中途问答、继续和修改字段

审批流程进行中，如果用户问普通问题，例如“这个审批能撤回吗？”，后端会走 `general_chat` 回答问题，但不会清空当前审批状态。响应仍保持当前 `status`、`approval_type`、`awaiting_input`，并在 `assistant_message` 后附加当前等待项，例如：

```text
提交后能否撤回取决于审批配置。

继续刚才的审批，当前等待填写：数量。
```

用户回复“继续”“继续审批”“回到刚才审批”等，会直接返回当前等待项，不重新搜索模板。

字段修改支持两种方式：

- 前端结构化修改：下一轮请求带 `answer.field_key`，如果该字段已收集，会覆盖旧值。
- 自然语言修改：例如“金额改成3000”，规则或 LLM 能抽取到字段时会覆盖旧值。

修改字段后，后端会清理依赖字段，避免旧值误提交。例如：

```text
start_date -> 清理 end_date
rest_start_time -> 清理 rest_end_time、rest_duration
go_out_start_time -> 清理 go_out_end_time、go_out_duration
```

预览阶段修改字段后不会提交，会重新进入 `collect -> validate -> assignee -> preview` 链路，生成新的预览。

### 7.5 时光回溯接口

每次 `POST /api/ai-approval/chat` 成功处理后，后端都会保存一份内存 checkpoint。这个能力用于学习和调试：可以看某轮对话结束后的完整状态，也可以恢复到历史点继续跑，或者分叉成一个新 `session_id` 做对比实验。

列出 checkpoint：

```bash
curl -s "http://127.0.0.1:8010/api/ai-approval/time-travel/S-demo/checkpoints?user_id=U001"
```

查看详情：

```bash
curl -s "http://127.0.0.1:8010/api/ai-approval/time-travel/S-demo/checkpoints/ckpt_xxx?user_id=U001"
```

恢复当前会话：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/time-travel/S-demo/restore \
  -H 'Content-Type: application/json' \
  -d '{"checkpoint_id":"ckpt_xxx","user_id":"U001"}'
```

从历史点分叉新会话：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/time-travel/S-demo/fork \
  -H 'Content-Type: application/json' \
  -d '{"checkpoint_id":"ckpt_xxx","user_id":"U001","new_session_id":"S-demo-branch"}'
```

当前实现是学习版内存 checkpoint，不依赖数据库；服务重启后 checkpoint 会丢失。接口返回的状态会脱敏 `authorization`、`token`、`password` 等字段，但恢复到内部 session 时仍保留原状态，方便继续调试。

## 8. 调试方式

### 8.1 Swagger 调试

打开：

```text
http://127.0.0.1:8010/docs
```

选择 `POST /api/ai-approval/chat`，点击 `Try it out`，填入请求 JSON。

### 8.2 curl 调试

发起报销：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-demo-expense","user_id":"U001","message":"我要报销餐饮费 2000 元，客户招待，发票已提供"}'
```

确认提交：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-demo-expense","user_id":"U001","message":"确认提交"}'
```

取消流程：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-demo-cancel","user_id":"U001","message":"我要采购笔记本电脑"}'

curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-demo-cancel","user_id":"U001","message":"取消"}'
```

### 8.3 看 trace

每次响应都有 `trace`：

```json
["memory_agent", "user_profile_agent", "intent_router", "approval_creation_agent", "load_context", "classify", "decision_review", "collect", "validate", "preview"]
```

常见节点：

| 节点 | 说明 |
|---|---|
| `memory_agent` | 写入本轮短期会话记忆 |
| `user_profile_agent` | 加载当前用户和直属上级等用户上下文 |
| `intent_router` | 在用户信息、普通聊天、审批发起等 Agent 之间路由 |
| `user_info_agent` | 回答当前用户、上级、部门等信息，不进入审批子流程 |
| `approval_creation_agent` | 审批发起子图入口 |
| `daily_report_form_agent` | 写日志主流程，加载日报页面上下文并等待前端表单回填 |
| `daily_report_chat_agent` | 写日志快捷流程，用用户消息生成简单日报内容 |
| `submit_daily_report` | 用户确认后提交日报 |
| `load_context` | 加载用户上下文和可用审批模板 |
| `classify` | 识别用户意图和审批类型 |
| `decision_review` | 有界决策复核，防止误提交或无限思考 |
| `collect` | 按模板收集字段 |
| `validate` | CRM 预校验 |
| `preview` | 生成审批预览 |
| `submit` | 创建审批申请 |
| `cancel` | 取消当前审批 |
| `clarify` | 追问澄清 |

### 8.4 看服务日志

启动服务后，终端会输出 Uvicorn 日志和应用请求日志。

示例：

```text
INFO [ai_approval_assistant.http] POST /api/ai-approval/chat -> 200 8.45ms
```

含义：

| 字段 | 说明 |
|---|---|
| `POST` | 请求方法 |
| `/api/ai-approval/chat` | 请求路径 |
| `200` | HTTP 状态码 |
| `8.45ms` | 接口处理耗时 |

现在日志实现位置：

```text
app/logging_config.py
app/middleware.py
```

接口日志会输出到控制台；AI 审批调试日志会写入 `logs/ai_approval_debug.log`。调试日志包含 `chat.request`、`chat.response` 和 CRM 请求/响应摘要，`Authorization` 会脱敏。

模型调用失败时，会写 warning 日志并自动回退规则逻辑，例如：

```text
WARNING [ai_approval_assistant.model] LLM slot extraction failed: ...
```

### 8.5 看测试日志

运行测试：

```bash
.venv/bin/python -m pytest tests -v
```

如果要看更详细失败信息：

```bash
.venv/bin/python -m pytest tests -vv
```

### 8.6 修改 mock 审批模板

模板文件：

```text
app/mock_data/approval_templates.py
```

每个审批模板有：

```python
{
    "approval_type": "seal",
    "title": "用章申请",
    "category": "行政",
    "intent_keywords": ["用章", "盖章", "公章", "合同章"],
    "fields": [
        {
            "name": "seal_type",
            "label": "印章类型",
            "type": "enum",
            "required": True,
            "options": ["公章", "合同章", "财务章"],
            "aliases": ["章类型", "印章"],
            "extract_patterns": [],
            "question": "请说明要使用的印章类型：公章、合同章、财务章。",
        }
    ],
}
```

真实 CRM 接入时，可以把 CRM 返回的审批模板映射成这个结构。

### 8.7 调试 Prompt

调试 prompt 的建议流程：

1. 复制 `prompts/approval_prompts.json` 到临时文件。
2. 设置 `AI_APPROVAL_PROMPT_FILE` 指向临时文件。
3. 设置 `AI_APPROVAL_USE_LLM=true` 和 `DEEPSEEK_API_KEY`。
4. 启动服务后，用 Swagger 或 curl 固定同一个 `session_id` 反复测试。
5. 看响应里的 `trace`、`approval_type`、`collected_slots`、`missing_fields` 和 `field_errors`。
6. 修改 prompt JSON 后重启服务，再重复请求。

重点观察：

| 现象 | 优先调整 |
|---|---|
| 审批类型选错 | `classification.system` 和 `classification.rules` |
| 多个相似审批误判 | `classification.rules`，要求低置信度返回 null |
| 字段抽错或编造 | `slot_extraction.system` 和 `slot_extraction.rules` |
| 枚举值不符合模板 | `slot_extraction.rules` |
| “好的/可以”被误提交 | `decision_review.rules` |

如果只是想确认 prompt 拼出来的结构，可以看测试：

```text
tests/test_model_prompts.py
```

这里会验证默认配置和 `AI_APPROVAL_PROMPT_FILE` 覆盖逻辑。

## 9. 演示脚本

### 9.1 演示报销审批

第一步：发起审批并生成预览。

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-1","user_id":"U001","message":"我要报销餐饮费 2000 元，客户招待，发票已提供"}'
```

预期：

- `status` 是 `awaiting_confirmation`
- `approval_type` 是 `expense`
- `actions` 包含 `confirm`
- `request_id` 还是 `null`

第二步：确认提交。

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-1","user_id":"U001","message":"确认提交"}'
```

预期：

- `status` 是 `submitted`
- 返回 `request_id`

### 9.2 演示缺字段追问

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-2","user_id":"U001","message":"我要采购笔记本电脑"}'
```

预期：

- `status` 是 `collecting`
- `awaiting_field` 是 `quantity`
- 系统追问采购数量

继续补充：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-2","user_id":"U001","message":"2台"}'
```

### 9.3 演示不同审批模板字段

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-3","user_id":"U001","message":"我要申请用公章，文件名称是销售合同，2份，用途是客户签约"}'
```

预期字段：

```json
{
  "seal_type": "公章",
  "document_name": "销售合同",
  "copies": "2",
  "purpose": "客户签约"
}
```

### 9.4 演示提交守卫

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-4","user_id":"U001","message":"确认提交"}'
```

预期：

- 不会创建审批
- `request_id` 是 `null`
- `trace` 包含 `decision_review`

### 9.5 演示普通聊天不会搜索审批模板

带真实 ERP 凭证时，普通问候仍然走通用聊天，不会调用 `/api/approval/list` 搜索 `你好`。

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-chat","user_id":"863","uid":"863","authorization":"Bearer your_token_here","message":"你好"}'
```

预期：

- `status` 是 `idle`
- `approval_type` 是 `null`
- `trace` 包含 `general_chat`
- 不会返回“没有找到审批模板”

帮助问句也走通用聊天：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-help","user_id":"863","uid":"863","authorization":"Bearer your_token_here","message":"怎么新增审批"}'
```

### 9.6 演示远程模板选择

用户输入明确模板关键词后，后端会调用 `/api/approval/list`：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-template","user_id":"863","uid":"863","authorization":"Bearer your_token_here","message":"测试外出"}'
```

如果命中多个模板，响应会包含：

```json
{
  "status": "idle",
  "awaiting_input": {
    "field_key": "__approval_template__",
    "label": "审批模板",
    "type": "single_select",
    "options": [
      { "label": "测试外出", "value": "remote_5911" }
    ]
  }
}
```

前端选择模板后，下一轮请求带 `answer`：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-template","user_id":"863","uid":"863","authorization":"Bearer your_token_here","message":"测试外出","answer":{"field_key":"__approval_template__","type":"single_select","label":"测试外出","value":"remote_5911"}}'
```

模板选择阶段用户回复 `取消` 会取消本次流程并清空候选模板。

### 9.7 演示结构化字段填写

请假类型这类动态单选字段会返回 `single_select`。前端选择后，回传 label 和真实 value：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-field","user_id":"863","uid":"863","authorization":"Bearer your_token_here","message":"调休假","answer":{"field_key":"rest_holiday_rule_id","type":"single_select","label":"调休假（余8小时）","value":11}}'
```

日期时间字段：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-field","user_id":"863","uid":"863","authorization":"Bearer your_token_here","message":"2026-06-13 09:00","answer":{"field_key":"rest_start_time","type":"datetime","label":"2026-06-13 09:00","value":"2026-06-13 09:00:00"}}'
```

地址字段：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-field","user_id":"863","uid":"863","authorization":"Bearer your_token_here","message":"上海市浦东新区张江路88号","answer":{"field_key":"go_out_addr","type":"address","label":"上海市浦东新区张江路88号","value":{"area":["上海市","浦东新区"],"detail":"张江路88号"}}}'
```

### 9.8 演示审批人选择和提交

必填字段收集完并通过校验后，后端会调用 `/api/approval/getNodes`。如果流程节点需要发起人选择办理人，会返回：

```json
{
  "status": "awaiting_assignee_selection",
  "awaiting_input": {
    "field_key": "__approval_assignee__:12204",
    "label": "办理审批人",
    "type": "user_select",
    "options": [
      { "label": "张三", "value": "864", "avatar": null }
    ],
    "multiple": false
  }
}
```

前端选择后回传：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-field","user_id":"863","uid":"863","authorization":"Bearer your_token_here","message":"张三","answer":{"field_key":"__approval_assignee__:12204","type":"user_select","label":"张三","value":"864"}}'
```

随后进入 `awaiting_confirmation`，用户明确回复：

```bash
curl -s -X POST http://127.0.0.1:8010/api/ai-approval/chat \
  -H 'Content-Type: application/json' \
  -d '{"session_id":"S-show-field","user_id":"863","uid":"863","authorization":"Bearer your_token_here","message":"确认提交"}'
```

提交时后端会组装 `/api/approval/add` 需要的 `form_data` 和 `node_list`，并把已选办理人写入对应节点的 `handle_uids`、`handle_uids_info`。

## 10. 查看流程图

业务会话级流程图：

```text
docs/session_flow.mmd
```

可以把内容粘贴到 Mermaid Live Editor：

```text
https://mermaid.live/
```

也可以在支持 Mermaid 的 Markdown 工具中打开。

如果想重新导出 LangGraph 节点图：

```bash
.venv/bin/python scripts/export_graph.py
```

会生成：

```text
docs/approval_graph.mmd
```

如果不需要该图，可以删除生成文件，不影响代码运行。

## 11. LangGraph Studio 调试

项目根目录已提供 `langgraph.json`，Studio graph 入口是：

```text
app.graph.studio:graph
```

本地启动：

```powershell
cd D:\PythonProject\LearnOne\ai_approval_assistant
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\langgraph.exe dev
```

也可以在 `.env` 配置 `AI_APPROVAL_STUDIO_ENABLED=true`，然后用 `.\start_windows.ps1` 同时启动 FastAPI 和 Studio。

Studio 顶层图展示的是多 Agent 编排：`memory_agent -> user_profile_agent -> intent_router`，再按意图进入 `user_info_agent`、`general_chat`、`approval_creation_agent`、`daily_report_form_agent` 或 `daily_report_chat_agent`。`load_context`、`classify`、`collect` 等审批细节已经收敛在 `approval_creation_agent` 子图里；写日志/日报的字段加载和提交确认收敛在日报 agent 里；普通问候、帮助问句和“我的用户信息是什么”不会经过审批节点。

如果当前环境没有 LangGraph CLI，可以先同步开发依赖：

```powershell
uv sync --dev
```

Studio 里直接调的是 `ApprovalState`，不是 FastAPI 的 `ChatRequest`。调试示例放在：

```text
app/graph/studio.py
```

可用示例：

- `STUDIO_EXAMPLES["new_purchase"]`：从 0 开始采购审批。
- `STUDIO_EXAMPLES["new_expense"]`：从 0 开始报销审批。
- `STUDIO_EXAMPLES["resume_collecting"]`：模拟已在收集字段中的会话。

ERP 能力也封装成了现代 `@tool` 工具，位置：

```text
app/tools/approval_tools.py
```

当前工具：

- `search_approval_templates`
- `get_approval_form_fields`
- `get_holiday_rule_options`
- `get_related_business_options`

这些工具先作为 Studio/后续 agent 化调试边界，不改变现有 `/api/ai-approval/chat` 的确定性审批主流程。

## 12. 运行测试

```bash
.venv/bin/python -m pytest tests
```

当前预期：

```text
77 passed
```

## 13. 后续接真实 CRM

主要替换：

```text
app/services/crm_service.py
```

需要对接的真实能力：

- 获取当前登录用户上下文。
- 获取当前用户可发起审批模板列表。
- 获取审批模板详情。
- 审批字段预校验。
- 创建审批申请。
- 查询审批状态。

注意事项：

- 真实环境不要信任前端传入的 `user_id`，应从登录态或 token 解析。
- 当前 mock 已有基础幂等键；真实 CRM 接入时要把幂等键传给创建审批接口。
- 当前 mock 已返回字段级错误；真实 CRM 预校验也建议返回字段级错误，方便聊天继续追问。
- 有附件的字段需要单独设计上传和绑定逻辑。
- 如果 CRM 模板很多，不要把全部模板直接塞给 LLM；应先按分类、常用、关键词、别名筛出候选模板。

## 14. 当前实现用了哪些技术

### 14.1 FastAPI API 层

入口：

```text
app/main.py
```

路由：

```text
app/api/health.py
app/api/chat.py
```

职责：

- 暴露 HTTP 接口。
- 接收请求。
- 调用 LangGraph 工作流。
- 返回 Pydantic 响应。

### 14.2 Pydantic Schema

位置：

```text
app/schemas/
```

职责：

- 定义聊天请求和响应。
- 定义审批模板字段。
- 定义 CRM 用户上下文、预校验结果、提交结果。

### 14.3 LangGraph 流程编排

位置：

```text
app/graph/workflow.py
```

顶层 Agent 节点：

```text
memory_agent
user_profile_agent
intent_router
user_info_agent
general_chat
approval_creation_agent
daily_report_form_agent
daily_report_chat_agent
```

`approval_creation_agent` 子图节点：

```text
load_context
classify
decision_review
collect
validate
assignee
preview
submit
already_submitted
cancel
clarify
general_chat
```

职责：

- 管理每轮聊天审批的状态流转。
- 普通聊天和帮助问句走 `general_chat`，不会误触发模板搜索。
- 明确审批意图才进入模板搜索、字段收集和审批提交链路。
- 明确写日志/日报意图时进入日报 agent；默认走表单版，明确“快速/简单/直接”时走聊天快捷版。
- 控制提交前必须预览和确认。
- 控制需要发起人选择办理人/审批人时暂停，并返回 `user_select`。
- 控制有界复核，避免无限思考。

### 14.3.1 日报 Agent 编排

位置：

```text
app/agents/daily_report_form_agent.py
app/agents/daily_report_chat_agent.py
app/agents/daily_report_common.py
app/services/daily_report_service.py
app/services/daily_report_api_client.py
app/schemas/daily_report.py
```

当前有两个写日志方案：

- `daily_report_form_agent`：主路径。用户说“写今天日报/写日志”时，后端请求日报表单字段、日报设置、当天草稿和同步数据，然后返回 `ui_action.type=open_daily_report_form`。前端负责弹出正常写日志表单并收集完整 payload，包括自定义字段 `extends` 和 `extend_fields`。
- `daily_report_chat_agent`：快捷路径。用户明确说“快速写日报/简单写日报/直接按这段写日报”时，用当前消息生成简单日报内容，适合无复杂自定义字段的场景。

日报相关接口：

| 接口 | 方法 | 用途 |
|---|---|---|
| `/api/field/formFields` | POST | 获取 `daily_reports` 自定义字段 |
| `/oa/dailyReport/config/get?need_parse=1` | GET | 获取日报配置 |
| `/oa/dailyReport/draft/get?type=1&date=YYYY-MM-DD` | GET | 获取当天草稿 |
| `/api/oa/dailyReport/syncData` | POST | 获取流程、跟进、订单、工单、客户管理等同步数据 |
| `/oa/dailyReport/add` | POST | 用户确认后提交日报 |

知识点：

- 动态表单不要在聊天里硬编码控件逻辑；复杂字段由前端原生日报表单收集，agent 只负责加载上下文、预览和确认提交。
- 自定义字段必须完整透传 `extends` 和 `extend_fields`，否则提交接口无法还原用户填写的动态字段。
- 写入类操作必须有确认守卫：预览后用户明确回复“确认提交”才调用 `/oa/dailyReport/add`。
- 顶层 graph 只展示业务 agent，具体业务内部步骤收敛在各自 agent/service 中，避免 Studio 图被细节淹没。

### 14.4 模板驱动字段收集

位置：

```text
app/graph/extractors.py
app/mock_data/approval_templates.py
```

工作方式：

- 模板支持 `category`、`group_name`、`aliases`、`visibility`、`enabled`、`is_common`、`sort_order` 等元数据。
- 远程模板搜索只在明确审批意图或模板关键词时触发，普通问候和帮助问句走通用聊天。
- 多个远程模板命中时返回 `awaiting_input.type=single_select`，由前端选择模板后继续收集字段。
- 审批类型先按模板标题、分类、分组、别名、关键词做候选筛选。
- 规则识别和 LLM 识别都只处理候选模板，避免真实审批库过大导致 prompt 膨胀。
- 审批类型由模板的 `intent_keywords`、`aliases`、枚举选项等信息匹配。
- 字段由模板的 `fields` 决定。
- 枚举字段从 `options` 抽取。
- 文本、日期、数字字段可以用 `extract_patterns` 抽取。
- 缺字段时返回模板里的 `question`。
- 如果开启 `AI_APPROVAL_USE_LLM=true`，审批类型规则识别不到时，会调用 DeepSeek 从当前可用 CRM 模板中选择审批类型。
- 如果开启 `AI_APPROVAL_USE_LLM=true`，字段收集会先用规则抽取，再调用 DeepSeek 补充规则没有抽到的字段。

### 14.5 CRM 适配层

位置：

```text
app/services/crm_service.py
```

当前是 mock 实现。后续真实接入时替换这里。

当前方法：

```text
get_user_context
list_available_templates
search_available_templates
get_template_detail
validate_approval
get_approval_nodes
submit_approval
```

真实 ERP 模式下当前调用：

- `/api/approval/list`：按关键词查模板。
- `/api/field/formFields`：按 `approval_type_{id}` 查表单字段。
- `/api/attendance/getHolidayRuleByUser`：按字段映射拉请假类型等动态单选。
- `/api/Company/getRelatedList`：按字段映射拉关联业务对象。
- `/api/approval/getNodes`：字段完整后获取审批流程节点。
- `/api/approval/add`：确认提交后创建审批。

CRM 适配层会为每个接口记录：

- request：脱敏后的请求头和请求体。
- response：响应 code、message、数据类型和少量样例。
- timing：`duration_ms`、`success`、`status_code`、错误摘要。

模板详情、请假类型和关联对象列表都有 TTL 缓存。缓存 key 会带上 `uid` 或 `user_id`，避免不同用户权限下互相复用。

### 14.6 会话状态

位置：

```text
app/services/session_state_service.py
```

当前支持两种保存方式：

```text
memory: session_id -> ApprovalState
redis:  {REDIS_PREFIX}ai_approval:session:{session_id} -> ApprovalState JSON
```

默认优先使用 Redis；没有配置 Redis 或 Redis 不可用时自动回退内存。会话 Redis TTL 由 `AI_APPROVAL_SESSION_TTL_SECONDS` 控制，默认 7200 秒。

### 14.6.1 时光回溯 checkpoint

位置：

```text
app/services/time_travel_service.py
app/api/time_travel.py
app/schemas/time_travel.py
```

当前实现是学习版的内存 checkpoint：

- `run_chat_turn` 在每轮会话保存后调用 `time_travel_service.record(...)`。
- checkpoint 保存 `session_id`、`user_id`、轮次、用户消息、状态、意图、trace 摘要和一份深拷贝后的 `ApprovalState`。
- `restore` 会把某个 checkpoint 的状态写回原 `session_id`。
- `fork` 会把某个 checkpoint 的状态复制到新的 `session_id`，适合对比不同后续输入。
- API 返回状态时会脱敏凭证字段，内部恢复仍使用原始状态。

知识点：

- LangGraph 的“时光回溯”本质是状态快照 + 线程标识 + checkpoint 选择。本项目先用项目自有服务模拟这个概念，代码更容易读。
- checkpoint 和当前 session state 是两份深拷贝，后续聊天不会悄悄修改历史快照。
- 生产化可以把 `TimeTravelService` 换成 Redis、文件或 LangGraph 原生 checkpointer；API 和 agent 挂点可以保持基本不变。

### 14.7 日志

位置：

```text
app/logging_config.py
app/middleware.py
```

当前能力：

- 请求方法
- 请求路径
- HTTP 状态码
- 接口耗时
- CRM/ERP 接口 request、response、timing 日志

聊天 debug 日志还会记录：

- `session_id`
- `user_id`
- `approval_type`
- `status`
- `trace`

### 14.8 DeepSeek LLM 层

位置：

```text
app/services/model_service.py
```

当前接入点：

- 审批类型识别：`classify_approval_type`
- 字段抽取：`extract_slots`
- 决策复核：`review_decision`

Prompt 构建函数：

```text
build_classification_prompt
build_slot_extraction_prompt
build_decision_review_prompt
```

Prompt 设计原则：

- 审批类型识别只接收候选模板，不接收完整模板库。
- 候选模板摘要包含模板 ID、标题、分类、分组、别名、关键词、常用标记和字段摘要。
- 字段抽取只能输出当前模板字段，不能根据常识补全。
- 字段抽取默认不覆盖已收集字段，除非用户本轮明确修改。
- 决策复核只允许输出 `collect`、`submit`、`cancel`、`clarify`。
- 硬规则优先：没有预览不能提交，没有明确“确认提交”不能提交。

环境变量：

| 变量 | 说明 |
|---|---|
| `AI_APPROVAL_USE_LLM` | 是否启用真实 LLM 请求，必须是 `true` 才会调用 |
| `DEEPSEEK_API_KEY` | DeepSeek API Key |
| `DEEPSEEK_MODEL` | 模型名，默认 `deepseek-chat` |
| `DEEPSEEK_TEMPERATURE` | 温度，审批场景建议 `0` |
| `DEEPSEEK_TIMEOUT` | 超时时间，默认 30 秒 |

安全约束：

- LLM 只负责抽取和复核，不直接提交审批。
- LLM 只能从当前 CRM 返回的可用审批模板中选择审批类型。
- LLM 输出字段必须落在当前审批模板字段内。
- LLM 失败时自动回退规则逻辑。
- CRM 预校验和提交守卫始终由后端确定性代码执行。

## 15. 还需要修改和完善的地方

### 15.1 接真实 CRM

优先级最高。

需要把 mock 的：

```text
app/mock_data/approval_templates.py
```

替换为真实 CRM 返回，或者在 `crm_service.py` 中把真实 CRM 模板映射成当前 `ApprovalTemplate`。

需要真实接口：

- 当前用户上下文。
- 当前用户可发起审批模板。
- 审批模板详情。
- 审批字段预校验。
- 创建审批。
- 查询审批状态。

### 15.2 身份认证

当前接口直接接收：

```json
{
  "user_id": "U001"
}
```

真实环境不能信任前端传入的 `user_id`，应该从登录态、JWT、网关 Header 或后端 session 解析用户身份。

### 15.3 Redis 会话存储

已支持 Redis 会话存储：

- key：`{REDIS_PREFIX}ai_approval:session:{session_id}`
- value：序列化后的 `ApprovalState`
- TTL：`AI_APPROVAL_SESSION_TTL_SECONDS`，默认 7200 秒

本地没有 Redis 时会自动回退内存。生产环境建议明确配置：

```text
AI_APPROVAL_SESSION_BACKEND=redis
AI_APPROVAL_SESSION_TTL_SECONDS=7200
REDIS_HOST=...
REDIS_PORT=6379
REDIS_PASSWORD=...
REDIS_PREFIX=lanerp20_local_
```

### 15.4 幂等提交

当前 mock 提交已经生成并保存 `idempotency_key`，同一会话同一审批内容重复确认时会复用提交结果。

真实 CRM 接入时仍需把幂等键传给 CRM 创建审批接口，例如：

```text
session_id + approval_type + preview_hash
```

避免用户重复点击、网络重试、重复说“确认提交”导致创建多张审批单。

### 15.5 复杂字段和附件字段

当前 `_child` 控件组会先展开，快速发起只收集必填子字段。子字段会保留父级元数据：

- `group_key`
- `group_label`
- `group_type`

其中 `detail/detail_table/table` 会标记成 `detail_table`，其他父控件标记成 `complex_group`。这样后续组装提交数据时可以知道字段来自哪个复杂控件。

当前主要支持文本、数字、日期、枚举、地址、用户选择和单选。真实审批还可能需要：

- 发票附件
- 合同附件
- 图片
- PDF
- 多行明细表

建议附件单独走上传接口，再把附件 ID 写入审批字段。

### 15.6 字段抽取能力

当前字段抽取是规则 + 可选 DeepSeek。

后续需要继续完善：

- 输入：用户消息 + 当前审批模板 + 已收集字段。
- 输出：JSON slots。
- 要求：只能输出模板中存在的字段。
- 防护：LLM 抽取后仍要 CRM 预校验。

### 15.7 decision_review 接 LLM

当前 `decision_review` 已支持可选 LLM 复核。

后续需要补更严格的复核评估：

- 当前意图是否明确。
- 是否真的要切换审批类型。
- 是否满足提交条件。
- 用户表达是否只是“好的”而不是明确确认。

必须保留：

- 最大复核次数。
- 不确定就澄清。
- 未预览不提交。
- 未明确确认不提交。

### 15.8 字段级错误处理

当前 mock 预校验已经同时返回字符串错误和字段级错误。

真实 CRM 建议保持字段级错误结构：

```json
{
  "field": "amount",
  "message": "报销金额超过当前用户权限上限"
}
```

这样聊天可以准确追问或要求修改某个字段。

### 15.9 日志和可观测

当前只有基础请求日志。

建议增加：

- JSON 结构化日志。
- CRM 调用日志。
- 节点流转日志。
- 错误堆栈日志。
- 敏感字段脱敏。
- LangSmith trace，后续接 LLM 时使用。

### 15.10 测试覆盖

当前测试覆盖了主流程。

后续还需要补：

- 审批类型切换。
- 修改字段后重新预览。
- 预校验失败。
- CRM 超时。
- CRM 500。
- 用户无权限。
- 重复确认提交。
- 附件缺失。

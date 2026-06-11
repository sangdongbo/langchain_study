# AI Approval Assistant

接口版 AI 聊天审批助手。

当前目录是独立后端骨架，只参考 `docs/ai_approval` 中的方案，不依赖仓库里的其他 demo 目录。第一版用 mock CRM 数据演示整体链路，后续接真实 CRM 时主要替换 `app/services/crm_service.py`。

## 1. 功能范围

- `GET /health`：健康检查。
- `POST /api/ai-approval/chat`：聊天审批主接口。
- 按 `session_id` 保存多轮审批会话状态。
- 从 mock CRM 获取当前用户可发起的审批模板。
- 按审批模板动态收集字段。
- 缺字段时在聊天里逐项追问。
- 字段完整后调用 CRM 预校验。
- 生成审批预览。
- 用户明确回复“确认提交”后才创建审批。
- 支持取消、修改和确认提交守卫。
- 支持有界决策复核 `decision_review`，避免无限反复思考。

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
- LangGraph：审批会话流程编排。
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
│   ├── mock_data/
│   │   └── approval_templates.py
│   ├── schemas/
│   │   ├── approval.py
│   │   └── chat.py
│   ├── services/
│   │   ├── crm_service.py
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

脚本会先在 `ai_approval_assistant` 内执行 `uv sync` 安装/同步本项目 `pyproject.toml` 里声明的依赖，然后用 `.venv\Scripts\python.exe` 启动服务。环境变量放在 `.env`，可参考 `.env.example`。默认地址仍然是：

```text
http://127.0.0.1:8010
```

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
  "message": "我要报销餐饮费 2000 元，客户招待，发票已提供"
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

传入 `uid` 和 `authorization` 后，后端会先调用真实 ERP 的审批列表接口：

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

响应核心字段：

| 字段 | 说明 |
|---|---|
| `status` | 当前流程状态 |
| `assistant_message` | 返回给用户看的文本 |
| `approval_type` | 当前匹配到的审批类型 |
| `collected_slots` | 已收集字段 |
| `missing_fields` | 当前缺失字段 |
| `awaiting_field` | 正在等待用户补充的字段 |
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
| `awaiting_confirmation` | 字段完整，等待用户确认提交 |
| `submitted` | 已提交审批 |
| `cancelled` | 已取消 |
| `error` | 出错 |

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
["load_context", "classify", "decision_review", "collect", "validate", "preview"]
```

常见节点：

| 节点 | 说明 |
|---|---|
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

## 11. 运行测试

```bash
.venv/bin/python -m pytest tests
```

当前预期：

```text
36 passed
```

## 12. 后续接真实 CRM

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

## 13. 当前实现用了哪些技术

### 13.1 FastAPI API 层

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

### 13.2 Pydantic Schema

位置：

```text
app/schemas/
```

职责：

- 定义聊天请求和响应。
- 定义审批模板字段。
- 定义 CRM 用户上下文、预校验结果、提交结果。

### 13.3 LangGraph 流程编排

位置：

```text
app/graph/workflow.py
```

当前节点：

```text
load_context
classify
decision_review
collect
validate
preview
submit
cancel
clarify
```

职责：

- 管理每轮聊天审批的状态流转。
- 控制提交前必须预览和确认。
- 控制有界复核，避免无限思考。

### 13.4 模板驱动字段收集

位置：

```text
app/graph/extractors.py
app/mock_data/approval_templates.py
```

工作方式：

- 模板支持 `category`、`group_name`、`aliases`、`visibility`、`enabled`、`is_common`、`sort_order` 等元数据。
- 审批类型先按模板标题、分类、分组、别名、关键词做候选筛选。
- 规则识别和 LLM 识别都只处理候选模板，避免真实审批库过大导致 prompt 膨胀。
- 审批类型由模板的 `intent_keywords`、`aliases`、枚举选项等信息匹配。
- 字段由模板的 `fields` 决定。
- 枚举字段从 `options` 抽取。
- 文本、日期、数字字段可以用 `extract_patterns` 抽取。
- 缺字段时返回模板里的 `question`。
- 如果开启 `AI_APPROVAL_USE_LLM=true`，审批类型规则识别不到时，会调用 DeepSeek 从当前可用 CRM 模板中选择审批类型。
- 如果开启 `AI_APPROVAL_USE_LLM=true`，字段收集会先用规则抽取，再调用 DeepSeek 补充规则没有抽到的字段。

### 13.5 CRM 适配层

位置：

```text
app/services/crm_service.py
```

当前是 mock 实现。后续真实接入时替换这里。

当前方法：

```text
get_user_context
list_available_templates
get_template_detail
validate_approval
submit_approval
```

### 13.6 会话状态

位置：

```text
app/services/session_state_service.py
```

当前是内存保存：

```text
session_id -> ApprovalState
```

本地演示可用。生产环境需要替换成 Redis 或数据库。

### 13.7 日志

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

后续建议扩展：

- `session_id`
- `user_id`
- `approval_type`
- `status`
- `trace`
- CRM 请求耗时和错误

### 13.8 DeepSeek LLM 层

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

## 14. 还需要修改和完善的地方

### 14.1 接真实 CRM

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

### 14.2 身份认证

当前接口直接接收：

```json
{
  "user_id": "U001"
}
```

真实环境不能信任前端传入的 `user_id`，应该从登录态、JWT、网关 Header 或后端 session 解析用户身份。

### 14.3 Redis 会话存储

当前会话状态在内存里：

- 服务重启后状态丢失。
- 多实例部署无法共享状态。

生产建议换成 Redis：

- key：`ai_approval:session:{session_id}`
- value：序列化后的 `ApprovalState`
- TTL：例如 30 分钟或 2 小时

### 14.4 幂等提交

当前 mock 提交已经生成并保存 `idempotency_key`，同一会话同一审批内容重复确认时会复用提交结果。

真实 CRM 接入时仍需把幂等键传给 CRM 创建审批接口，例如：

```text
session_id + approval_type + preview_hash
```

避免用户重复点击、网络重试、重复说“确认提交”导致创建多张审批单。

### 14.5 附件字段

当前只支持文本、数字、日期、枚举。

真实审批可能需要：

- 发票附件
- 合同附件
- 图片
- PDF

建议附件单独走上传接口，再把附件 ID 写入审批字段。

### 14.6 字段抽取能力

当前字段抽取是规则 + 可选 DeepSeek。

后续需要继续完善：

- 输入：用户消息 + 当前审批模板 + 已收集字段。
- 输出：JSON slots。
- 要求：只能输出模板中存在的字段。
- 防护：LLM 抽取后仍要 CRM 预校验。

### 14.7 decision_review 接 LLM

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

### 14.8 字段级错误处理

当前 mock 预校验已经同时返回字符串错误和字段级错误。

真实 CRM 建议保持字段级错误结构：

```json
{
  "field": "amount",
  "message": "报销金额超过当前用户权限上限"
}
```

这样聊天可以准确追问或要求修改某个字段。

### 14.9 日志和可观测

当前只有基础请求日志。

建议增加：

- JSON 结构化日志。
- CRM 调用日志。
- 节点流转日志。
- 错误堆栈日志。
- 敏感字段脱敏。
- LangSmith trace，后续接 LLM 时使用。

### 14.10 测试覆盖

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

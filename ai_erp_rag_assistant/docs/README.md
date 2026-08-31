# AI ERP RAG Assistant

这个项目实现 **RAG + ERP Tool + LangGraph** 三层协作，不是脱离 ERP 的知识库聊天。

## PDF 识别与数据位置

原始 PDF 位于：

```text
data/knowledge/source/北京澜景科技有限公司员工手册（2026修订版）.pdf
```

执行识别：

```powershell
uv sync --dev
uv run python scripts/ingest_pdf.py
```

脚本会：

1. 逐页读取 PDF。
2. 检查空白页，避免扫描页被静默忽略；当前版本不包含 OCR，扫描件需要先生成文字层。
3. 优先在句末或章节边界切分 Chunk，并保留页码、标题、原文件名、版本、生效日期和权限标签。
4. 输出 `data/knowledge/processed/employee_handbook_2026_chunks.jsonl`。
5. 输出 `data/knowledge/processed/parse_report.json`。

这份员工手册已验证为 22 页，22 页均可提取文本。原始 PDF 不放进 Prompt；JSONL 也不是最终知识库，而是可审查、可重建的中间结果。

## Milvus 持久化

当前 Docker 容器 `milvus-standalone` 已使用宿主机 bind mount：

```text
D:\PythonProject\LearnOne\docker\milvus-embed\volumes\milvus
  -> /var/lib/milvus
```

因此 Milvus 数据不依赖容器可写层，容器重启后仍可保留。当前容器：

- `milvus-standalone`：`127.0.0.1:19530`，healthy
- `attu`：`127.0.0.1:3000`

不要删除或清空上述目录。项目配置默认连接现有 Milvus，不会自动重建、删除或清空 collection。
写入和检索前会校验已有 Collection 的 `dense` 向量维度；当前 Embedding 为 2048 维时，
如果 Collection 使用其他维度，接口会直接返回配置不匹配错误。

## 三层边界

| 层 | 负责内容 | 示例 |
|---|---|---|
| RAG / Milvus | 制度、SOP、字段说明、审批规则 | 病假需要什么材料 |
| ERP Tool | 当前用户、审批模板、实时状态、业务数据 | 我的审批到谁了 |
| LangGraph | 路由、追问、校验、预览、确认、审计 | 帮我发起请假 |

RAG 不负责实时审批状态，ERP Tool 不替代制度知识，真实写入必须经过 LangGraph 确认闸门。

## 启动

```powershell
Copy-Item .env.example .env
uv sync --no-dev
uv run python scripts/ingest_pdf.py
uv run python scripts/ingest_pdf.py --write-milvus
uv run uvicorn ai_erp_rag_assistant.app.main:app --app-dir .. --reload --port 8021
```

配置加载顺序为：系统环境变量 > 项目目录 `ai_erp_rag_assistant/.env` > 仓库根目录 `.env`，
`LLM_*`/`EMBEDDING_*` 为空时自动使用外层配置中的 DashScope 或 DeepSeek 变量。
DashScope 工作空间 Key 会复用 `DASHSCOPE_BASE_URL` 作为 Embedding 端点；如需单独端点，
直接填写 `EMBEDDING_BASE_URL`。

联调时可在 `.env` 中启用 LangSmith：

```dotenv
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=lsv2_pt_xxx
LANGSMITH_PROJECT=ai-erp-rag-assistant
```

重启服务后，`/api/chat` 的 LangGraph 节点、LLM 调用、耗时和异常会归入该项目，
并带有哈希后的 `thread_id` 便于串联多轮请求。ERP Authorization、token、API key
等字段会在客户端上传前脱敏；业务对话和 Graph 状态仍属于 trace 内容，联调环境应按
企业数据策略使用。`GET /health` 可检查 tracing、API key 和项目名是否已加载。

默认脚本只生成可审查 JSONL；只有显式追加 `--write-milvus` 才会调用 Embedding 并 upsert 到本项目的 `erp_knowledge_chunks` collection。该命令不会删除或重建任何 collection。

当前已经完成一次真实入库：23 个 Chunk，Embedding 使用 `text-embedding-v4`，Milvus 使用 Docker Standalone 的持久化卷。检索请求会返回来源文件、页码、版本和权限元数据，再交给 LLM 生成带引用的答案。

知识检索会强制要求 `company_id`，并应用部门、有效状态和最低相关度过滤；不再依赖 ERP 返回本地自定义的知识库权限标签。

## RAG API

前端页面对接请优先阅读 [RAG_FRONTEND_API.md](RAG_FRONTEND_API.md)，其中包含请求头、
配置顺序、上传示例、搜索/问答响应和错误处理。

FastAPI 当前提供五个直接连接现有 Embedding、Milvus 和 LLM 服务的接口：

| 接口 | 作用 |
|---|---|
| `POST /api/rag/search` | 仅检索，返回 Chunk、来源、页码和得分 |
| `POST /api/rag/chat` | 检索后生成带引用的回答 |
| `POST /api/rag/ingest/text` | 将文本切分、Embedding 并写入知识库 |
| `POST /api/rag/ingest/pdf` | 读取原始 PDF 请求体并写入知识库 |
| `POST /api/rag/ingest/document` | 同步解析 PDF、DOCX、TXT、Markdown、JSON、CSV 等文档并写入知识库 |

搜索、问答和导入都强制要求 `company_id`。远程 ERP 模式下还必须提供 `UID` 和
`Authorization` 请求头，服务端会通过 ERP 用户信息校验请求公司，不能通过替换请求体中的
`company_id` 访问其他租户。`knowledge_base_key` 为空时兼容原有默认 Collection；不为空时，
服务端按 `company_id + knowledge_base_key` 生成独立且稳定的 Collection 名称。

检索示例：

```powershell
$headers = @{ UID = "863"; Authorization = "Bearer xxx" }
$body = @{
  query = "病假需要什么材料？"
  user_id = "863"
  company_id = "公司ID"
  knowledge_base_key = "employee_handbook"
  top_k = 5
} | ConvertTo-Json
Invoke-RestMethod -Method Post http://127.0.0.1:8021/api/rag/search `
  -Headers $headers -ContentType "application/json" -Body $body
```

文本入库示例：

```json
{
  "content": "需要入库的制度正文",
  "user_id": "863",
  "company_id": "公司ID",
  "knowledge_base_key": "employee_handbook",
  "source": "员工制度.txt",
  "title": "员工制度",
  "department": "公共制度",
  "version": "2026"
}
```

PDF 接口使用 `Content-Type: application/pdf` 的原始请求体，`company_id`、`user_id`、
`knowledge_base_key` 和 `source` 通过 Query 参数传入，单个文件限制为 20MB。扫描版 PDF
必须先生成文字层。

通用文档接口同样接收原始请求体，不需要 `python-multipart`。`source` 通过 Query 参数传入，
后缀用于选择解析器；支持 `.pdf`、`.docx`、`.txt`、`.md`、`.markdown`、`.json`、`.csv`、
`.xml` 和 `.html`。`permission_tags` 使用逗号分隔，`title`、`department`、`version`、
`effective_date`、`chunk_size` 和 `chunk_overlap` 也可通过 Query 参数覆盖。接口在一次请求内
完成文档解析、切分、Embedding 和 Milvus upsert，成功返回 `completed`、Chunk 数量、空页列表
和目标 Collection；单个文件限制为 20MB。

DOCX 正文和表格都会被提取，表格每行按 `列值 | 列值` 保留；JSON 会格式化为可检索文本，
CSV 会优先按首行表头生成 `字段: 值` 记录，HTML 会过滤 `script/style` 后只保留可见文本。

当 `knowledge_base_key` 已在管理 API 中配置时，未显式传入的 `chunk_size`、`chunk_overlap`
会自动采用该知识库的切分设置；Query 参数只用于本次导入临时覆盖。

通用文档导入示例：

```powershell
$headers = @{ UID = "863"; Authorization = "Bearer xxx" }
Invoke-RestMethod -Method Post `
  "http://127.0.0.1:8021/api/rag/ingest/document?company_id=公司ID&user_id=863&knowledge_base_key=employee_handbook&source=员工手册.docx&version=2026&permission_tags=hr,manager" `
  -Headers $headers -ContentType "application/vnd.openxmlformats-officedocument.wordprocessingml.document" `
  -InFile .\员工手册.docx
```

当前三个导入接口同步执行并直接返回 `completed`，不会向 MySQL 写文档或任务记录。
`ai_erp_knowledge_ingest_jobs` 和 `ai_erp_data_source_sync_jobs` 尚未用于持久化任务状态。配置 MySQL 后，接口会从
`ai_erp_knowledge_bases` 读取目标 Collection；未配置时继续使用原有确定性 Collection 名称。

## RAG 管理 API

管理接口位于 `/api/rag/admin`，同样通过 ERP `UID`、`Authorization` 校验真实
`company_id`。应用只映射已存在的表，不会自动建表或执行迁移。

| 接口 | 作用 |
|---|---|
| `POST /assistants`、`POST /assistants/list` | 创建、查询 Assistant |
| `POST /assistants/{id}/configs`、`POST /assistants/{id}/configs/list` | 创建、查询配置版本 |
| `POST /assistants/{id}/configs/{config_id}/publish` | 发布配置并归档旧发布版本 |
| `POST /assistants/{id}/prompts`、`POST /assistants/{id}/prompts/list` | 创建、查询 Prompt 版本 |
| `POST /assistants/{id}/prompts/{prompt_id}/publish` | 发布 Prompt 并归档同用途旧版本 |
| `POST /knowledge-bases`、`POST /knowledge-bases/list` | 创建、查询知识库 |
| `POST /data-sources`、`POST /data-sources/list` | 创建、查询文件、数据库或 API 数据源 |
| `POST /bindings/assistant-knowledge-base` | 绑定 Assistant 与知识库 |
| `POST /bindings/knowledge-base-source` | 绑定知识库与数据源 |

数据源的 `config`、`sync_config` 只能保存非敏感配置，密码、Token 和 API Key 必须使用
`credentials_ref` 指向外部密钥管理。要在问答时使用平台 Prompt，请在 `/api/rag/chat`
请求中同时传 `assistant_key`；服务端会读取已发布的 `knowledge_answer/primary` Prompt，
并校验该 Assistant 已绑定目标知识库。

Assistant 配置的 `model_config` 和 Prompt 的 `model_overrides` 会真正作用于 RAG 问答的
LLM 调用。Prompt 参数优先于 Assistant 配置，目前只支持 `model`、`temperature`（0..2）
和 `max_tokens`（1..100000）；API Key、Base URL、超时等连接参数只能由部署环境配置。
例如：

```json
{
  "model_config": {"model": "qwen-plus", "temperature": 0.2, "max_tokens": 2048}
}
```

MySQL 连接配置：

```dotenv
AI_ERP_MYSQL_HOST=127.0.0.1
AI_ERP_MYSQL_PORT=3306
AI_ERP_MYSQL_DATABASE=ai_erp
AI_ERP_MYSQL_USER=ai_erp_app
AI_ERP_MYSQL_PASSWORD=从部署环境注入
AI_ERP_MYSQL_CONNECT_TIMEOUT=5
```

ORM Model 覆盖 `001_mysql8_assistant_config.sql` 的 11 张 RAG 配置、文档和任务表。
当前管理 API 覆盖 Assistant、配置、Prompt、知识库、数据源及绑定；后台 Worker、
文档元数据和任务状态写入留到异步导入阶段。

ERP 接入有读写两个独立边界：

- `ERP_READ_MODE=remote`：使用真实 ERP 的 `/api/User/userinfo`、`/api/approval/list`、`/api/field/formFields`、`/api/approval/getNodes` 和审批状态接口；需要请求头 `UID`、`Authorization`。
- `ERP_WRITE_MODE=disabled`：演示默认值。可以读取真实模板、真实字段和审批节点，但确认后只返回预览，不调用 `/api/approval/add`。
- `ERP_READ_MODE=mock`、`ERP_WRITE_MODE=mock`：仅用于没有 ERP 服务时的离线排练，所有返回都会标记为 Mock。

接口契约与 `ai_approval_assistant` 一致：模板列表使用 `POST /api/approval/list` 和 `{"keyword": ...}`；字段使用 `POST /api/field/formFields` 和 `{"field_form": "approval_type_{id}"}`；节点使用 `POST /api/approval/getNodes` 和 `approval_set_id/form_value`；只有写入开启时才调用 `POST /api/approval/add`。

聊天响应中会返回 `workflow_status`、`plan`、`tool_calls`、`evidence`、`form_schema`、`preview`、`pending_question` 和 `erp_mode`。审批状态包括 `waiting_user`、`collecting_fields`、`waiting_assignee`、`waiting_erp`、`preview_ready`、`submitted`、`cancelled`、`blocked` 和 `failed`。

页面审批接口：

- `POST /api/approval/templates`：查询当前用户可用模板。
- `POST /api/approval/form-schema`：返回完整动态表单协议。
- `POST /api/approval/options`：按字段懒加载人员、部门和关联业务对象。
- `POST /api/chat`：提交自然语言或页面 `form_values`，生成冻结预览并确认提交。

页面不需要识别 ERP 的全部 `field_type`，只根据 `form_schema.fields[].component` 渲染。确认不了的字段由页面写入 `form_values`；自选审批人按节点 ID 写入 `selected_assignees`：

```json
{
  "message": "更新审批表单",
  "request_id": "前端每次操作生成的唯一ID",
  "assistant_key": "erp-rag",
  "session_id": "approval-001",
  "user_id": "863",
  "form_values": {
    "rest_holiday_rule_id": 12,
    "rest_content": "就医"
  },
  "selected_assignees": {
    "12204": ["864"]
  }
}
```

生产长期会话使用 `AI_ERP_SESSION_STORE=mysql`。启用前必须人工审查并执行 `docs/database/001`、`002`、`003`，同时为每家公司建立对应的 `AI_ERP_ASSISTANT_KEY`。启用后会话、消息、审批草稿、冻结预览、提交尝试和工具事件在同一事务写入；未配置时继续使用进程内状态。

前端长期会话接口：

- `POST /api/sessions/list`：按当前 ERP 用户分页读取会话，参数为 `status`、`page`、`page_size`。
- `POST /api/sessions/messages`：读取一个会话的消息，参数为 `session_id`、`before_seq`、`page_size`。

两个接口都会先通过 ERP `UID`、`Authorization` 确认用户和公司，再按
`company_id + assistant_key + ERP用户ID` 查询。请求体中的 `user_id` 不能用于读取其他用户的会话。

## LangGraph Studio

双击 `start_studio.bat` 即可同步开发依赖、启动本地 LangGraph API，并自动打开
LangSmith Studio。Studio API 默认使用 `http://127.0.0.1:2024`，与普通 FastAPI
服务的 `http://127.0.0.1:8021` 相互独立。

也可以从 PowerShell 启动：

```powershell
.\start_studio.ps1
```

Studio 会从 `langgraph.json` 加载 `erp_rag_assistant`。在 Studio 中实际运行节点时，
仍会使用 `.env` 中配置的 LLM、Milvus 和 ERP 环境；真实 ERP 写入继续受
`ERP_WRITE_MODE` 控制。普通 API 演示不依赖 Studio CLI。

## 示例请求

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8021/api/chat `
  -ContentType 'application/json' `
  -Body '{"message":"帮我明天下午请半天事假","user_id":"U001","session_id":"demo-001"}'
```

多轮审批示例：第一轮填写业务目标，第二轮补充 Graph 追问的必填字段，第三轮发送 `确认提交`（或请求体传 `confirm=true`）。只有确认节点才会调用 ERP 提交工具。确认冻结预览时，页面建议同时回传响应中的 `preview_id`、`preview_version` 和 `preview_hash`：

```json
{
  "message": "确认提交",
  "request_id": "confirm-approval-001-v1",
  "assistant_key": "erp-rag",
  "session_id": "approval-001",
  "user_id": "863",
  "confirm": true,
  "preview_id": "响应中的 preview_id",
  "preview_version": 1,
  "preview_hash": "响应中的 preview_hash"
}
```

如果页面确认的是旧版本，服务会拒绝提交并要求确认最新预览。显式确认会从工作流入口直接复用冻结的 `submission_fields`，不再调用 LLM、重新加载模板或重复校验显示值。

审批字段会在加载 ERP 动态模板后进行第二次结构化提取，并校验必填项、选项、日期时间和起止顺序。提交请求携带稳定的 `Idempotency-Key`，用于配合 ERP 服务端避免重复创建。

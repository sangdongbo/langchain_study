# AI ERP RAG Assistant

这个项目演示 **RAG + ERP Tool + LangGraph** 三层协作，不是脱离 ERP 的知识库聊天。

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

默认脚本只生成可审查 JSONL；只有显式追加 `--write-milvus` 才会调用 Embedding 并 upsert 到本项目的 `erp_knowledge_chunks` collection。该命令不会删除或重建任何 collection。

当前已经完成一次真实入库：23 个 Chunk，Embedding 使用 `text-embedding-v4`，Milvus 使用 Docker Standalone 的持久化卷。检索请求会返回来源文件、页码、版本和权限元数据，再交给 LLM 生成带引用的答案。

知识检索会强制要求 `company_id`，并应用部门、有效状态和最低相关度过滤；不再依赖 ERP 返回本地自定义的知识库权限标签。

ERP 接入有读写两个独立边界：

- `ERP_READ_MODE=remote`：使用真实 ERP 的 `/api/User/userinfo`、`/api/approval/list`、`/api/field/formFields`、`/api/approval/getNodes` 和审批状态接口；需要请求头 `UID`、`Authorization`。
- `ERP_WRITE_MODE=disabled`：演示默认值。可以读取真实模板、真实字段和审批节点，但确认后只返回预览，不调用 `/api/approval/add`。
- `ERP_READ_MODE=mock`、`ERP_WRITE_MODE=mock`：仅用于没有 ERP 服务时的离线排练，所有返回都会标记为 Mock。

接口契约与 `ai_approval_assistant` 一致：模板列表使用 `POST /api/approval/list` 和 `{"keyword": ...}`；字段使用 `POST /api/field/formFields` 和 `{"field_form": "approval_type_{id}"}`；节点使用 `POST /api/approval/getNodes` 和 `approval_set_id/form_value`；只有写入开启时才调用 `POST /api/approval/add`。

聊天响应中会返回 `plan`、`tool_calls`、`evidence`、`preview`、`pending_question` 和 `erp_mode`，可以直接展示 LLM Planner、Milvus、ERP Tool 和 LangGraph 的实际执行证据。

如需 LangGraph Studio，再单独安装与本机编译工具匹配的 `langgraph-cli[inmem]`；普通 API 演示不依赖 Studio CLI。

## 示例请求

```powershell
Invoke-RestMethod -Method Post http://127.0.0.1:8021/api/chat `
  -ContentType 'application/json' `
  -Body '{"message":"帮我明天下午请半天事假","user_id":"U001","session_id":"demo-001"}'
```

多轮审批示例：第一轮填写业务目标，第二轮补充 Graph 追问的必填字段，第三轮发送 `确认提交`（或请求体传 `confirm=true`）。只有确认节点才会调用 ERP 提交工具。

审批字段会在加载 ERP 动态模板后进行第二次结构化提取，并校验必填项、选项、日期时间和起止顺序。提交请求携带稳定的 `Idempotency-Key`，用于配合 ERP 服务端避免重复创建。

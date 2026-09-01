# RAG 前端接口文档

本文档给新建的 RAG 管理、文档导入、知识检索和问答页面使用。接口由
`ai_erp_rag_assistant` 的 FastAPI 提供。

## 1. 基本信息

开发环境默认地址：

```text
http://127.0.0.1:8021
```

除 `/health`、`/docs` 和 `/openapi.json` 外，业务接口路径都以 `/api` 开头。生产环境请把地址抽成前端环境变量：

```js
const API_BASE_URL = import.meta.env.VITE_RAG_API_BASE_URL;
```

FastAPI 自动生成的交互式接口页：`GET /docs`；原始 OpenAPI JSON：`GET /openapi.json`。
本文档是面向页面开发的稳定使用说明，字段发生变化时以服务端 OpenAPI 为准。

### 认证请求头

远程 ERP 模式推荐每次请求都带：

```http
UID: 863
Authorization: Bearer <ERP_TOKEN>
```

`company_id` 必须放在请求体或 Query 参数中，但服务端会用 ERP 返回的用户公司再次校验，
不能通过修改 `company_id` 访问其他公司。不要把 LLM、Embedding、Milvus、MySQL 或
LangSmith 的密钥放在浏览器代码中。

如果请求体同时带有 `uid` 或 `authorization`，服务端以 HTTP 请求头为准；请求头是当前
ERP 登录态，请求体字段只用于兼容旧页面。

前端请求封装示例：

```js
async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      UID: currentUser.uid,
      Authorization: currentUser.authorization,
      ...(options.body ? { "Content-Type": "application/json" } : {}),
      ...(options.headers || {}),
    },
  });

  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    const detail = payload.detail;
    const error = new Error(
      typeof detail === "string"
        ? detail
        : detail?.message || `请求失败（${response.status}）`,
    );
    error.detail = detail;
    throw error;
  }
  return payload;
}
```

文件上传接口的请求体是原始文件，不能使用上面的 JSON `Content-Type`。

## 2. 页面推荐流程

### 管理端首次配置

1. 创建 Assistant：`POST /api/rag/admin/assistants`
2. 创建 Assistant 配置版本：`POST /api/rag/admin/assistants/{assistant_id}/configs`
3. 发布配置：`POST /api/rag/admin/assistants/{assistant_id}/configs/{config_id}/publish`
4. 创建 Prompt 版本：`POST /api/rag/admin/assistants/{assistant_id}/prompts`
5. 发布 Prompt：`POST /api/rag/admin/assistants/{assistant_id}/prompts/{prompt_id}/publish`
6. 创建知识库：`POST /api/rag/admin/knowledge-bases`
7. 绑定 Assistant 和知识库：`POST /api/rag/admin/bindings/assistant-knowledge-base`
8. 上传文档：`POST /api/rag/ingest/document`

### 用户侧问答页面

1. 用户选择 `knowledge_base_key`。
2. 用户输入问题，调用 `POST /api/rag/chat`。
3. 使用 `message` 显示答案，使用 `evidence` 显示来源文件、页码和相关度。
4. 需要只看检索结果时调用 `POST /api/rag/search`，不调用 LLM。

没有 MySQL 配置时，搜索、问答和导入仍可以使用确定性的默认 Collection；管理接口
必须配置 MySQL，因为管理接口需要读写 Assistant、Prompt 和知识库配置表。

## 3. 健康检查

### `GET /health`

用于页面启动时检查服务配置，不需要请求体。

```js
const health = await fetch(`${API_BASE_URL}/health`).then((r) => r.json());
```

响应示例：

```json
{
  "status": "ok",
  "milvus_uri": "http://127.0.0.1:19530",
  "milvus_collection": "erp_knowledge_chunks_v2",
  "erp_mode": "remote",
  "erp_read_mode": "remote",
  "erp_write_mode": "disabled",
  "llm_configured": "true",
  "embedding_configured": "true",
  "mysql_configured": "false",
  "langsmith_tracing": "false"
}
```

前端只需要关注 `status`、`llm_configured`、`embedding_configured`、`mysql_configured`。
不要把响应中的内部地址或配置值展示给普通用户。

## 4. Assistant 管理接口

管理接口统一前缀：`/api/rag/admin`。所有管理请求 JSON 至少包含：

```json
{
  "company_id": "16",
  "user_id": "863"
}
```

也可以把 `uid`、`authorization` 放在 JSON 中，但推荐使用请求头。服务端最终以 ERP
校验后的用户和公司为准。

### 创建 Assistant

`POST /api/rag/admin/assistants`

```json
{
  "company_id": "16",
  "user_id": "863",
  "assistant_key": "employee-rag",
  "name": "员工制度助手"
}
```

响应状态为 `201`：

```json
{
  "item": {
    "id": 1,
    "company_id": "16",
    "assistant_key": "employee-rag",
    "name": "员工制度助手",
    "status": "active"
  }
}
```

### 查询 Assistant

`POST /api/rag/admin/assistants/list`

```json
{
  "company_id": "16",
  "user_id": "863",
  "status": "active"
}
```

响应：

```json
{
  "items": [],
  "count": 0
}
```

`status` 可选值为 `active`、`disabled`、`archived`。

### 编辑或停用 Assistant

`POST /api/rag/admin/assistants/{assistant_id}/update`

```json
{
  "company_id": "16",
  "user_id": "863",
  "name": "新版员工制度助手",
  "status": "active"
}
```

`name`、`status` 至少提交一个。`assistant_key` 是稳定业务标识，创建后不可修改；配置和
Prompt 内容也不在这里原地修改，仍通过创建新版本并发布完成。

### 创建配置版本

`POST /api/rag/admin/assistants/{assistant_id}/configs`

`model_config` 目前只允许 `model`、`temperature`、`max_tokens`，不能在这里保存 API Key、
Base URL、密码或 Token。`retrieval_config` 可配置召回数量、阈值和 LLM 重排。

```json
{
  "company_id": "16",
  "user_id": "863",
  "page_config": {},
  "model_config": {
    "model": "qwen3.7-plus",
    "temperature": 0.2,
    "max_tokens": 2048
  },
  "retrieval_config": {
    "top_k": 5,
    "score_threshold": 0.35,
    "rerank_enabled": true,
    "rerank_candidates": 15
  },
  "feature_flags": {}
}
```

响应状态为 `201`，返回 `item.id` 和配置版本状态。发布配置：

`POST /api/rag/admin/assistants/{assistant_id}/configs/{config_id}/publish`

请求体只需要 `company_id`、`user_id`。

查询配置版本：

`POST /api/rag/admin/assistants/{assistant_id}/configs/list`

### 创建和发布 Prompt

创建：`POST /api/rag/admin/assistants/{assistant_id}/prompts`

```json
{
  "company_id": "16",
  "user_id": "863",
  "prompt_key": "knowledge_answer",
  "variant": "primary",
  "content": "请用中文回答，并引用制度来源和页码。",
  "model_overrides": {
    "temperature": 0.1
  }
}
```

问答时使用的主 Prompt 约定为：

```text
prompt_key = knowledge_answer
variant = primary
status = published
```

发布：`POST /api/rag/admin/assistants/{assistant_id}/prompts/{prompt_id}/publish`

查询：`POST /api/rag/admin/assistants/{assistant_id}/prompts/list`

查询请求可以增加：

```json
{
  "prompt_key": "knowledge_answer",
  "variant": "primary"
}
```

## 5. 知识库管理接口

### 创建知识库

`POST /api/rag/admin/knowledge-bases`

```json
{
  "company_id": "16",
  "user_id": "863",
  "knowledge_key": "employee_handbook",
  "name": "员工手册",
  "description": "员工制度和考勤规则",
  "chunk_size": 800,
  "chunk_overlap": 120,
  "default_top_k": 5,
  "default_score_threshold": 0.35,
  "permission_config": {
    "allowed_departments": ["人力资源部"],
    "required_tags": ["employee"],
    "write_required_tags": ["knowledge:write"],
    "delete_required_tags": ["knowledge:admin"]
  }
}
```

Embedding 参数通常不需要前端传，服务端使用部署环境配置的模型和维度。当前默认要求：

```text
embedding_provider = openai-compatible
embedding_model = text-embedding-v4
embedding_dimension = 2048
```

响应状态为 `201`，返回的 `item.milvus_collection` 是实际目标 Collection。导入和搜索
使用 `knowledge_key`，前端可以将它保存为 `knowledge_base_key`。

### 查询知识库

`POST /api/rag/admin/knowledge-bases/list`

```json
{
  "company_id": "16",
  "user_id": "863",
  "status": "active"
}
```

### 编辑或停用知识库

`POST /api/rag/admin/knowledge-bases/{knowledge_base_id}/update`

```json
{
  "company_id": "16",
  "user_id": "863",
  "name": "员工制度知识库",
  "description": "员工制度、考勤和休假规则",
  "status": "active",
  "chunk_size": 900,
  "chunk_overlap": 120,
  "default_top_k": 8,
  "default_score_threshold": 0.4,
  "permission_config": {}
}
```

以上业务字段均可选，但至少提交一个。传空字符串可清空 `description`，传空对象可清空
`permission_config`。`knowledge_key`、`milvus_collection`、Embedding 模型和向量维度创建
后不可修改，避免新旧向量不兼容；需要更换这些参数时应新建知识库并重新导入文档。

### 绑定 Assistant 和知识库

`POST /api/rag/admin/bindings/assistant-knowledge-base`

```json
{
  "company_id": "16",
  "user_id": "863",
  "assistant_id": 1,
  "knowledge_base_id": 10,
  "enabled": true,
  "priority": 0,
  "retrieval_config": {
    "top_k": 5,
    "score_threshold": 0.35,
    "rerank_enabled": true,
    "rerank_candidates": 15
  },
  "permission_filter": {
    "any_tags": ["hr", "manager"]
  }
}
```

如果 `/api/rag/chat` 同时传了 `assistant_key` 和 `knowledge_base_key`，服务端会校验
Assistant 已绑定该知识库；未绑定会返回 `404`。

权限字段只使用 ERP 身份接口返回的部门、权限和角色，不信任前端请求中的权限标签。
`required_tags` 要求全部具备，`any_tags` 要求至少具备一个；`read_required_tags`、
`write_required_tags`、`delete_required_tags` 可以分别限制查询、导入和删除。知识库策略与
Assistant 绑定策略会依次校验，绑定配置不能放宽知识库本身的权限。

查询绑定：`POST /api/rag/admin/bindings/assistant-knowledge-base/list`

```json
{
  "company_id": "16",
  "user_id": "863",
  "assistant_id": 1,
  "knowledge_base_id": 10,
  "enabled": true
}
```

三个过滤字段均可省略，响应为 `{ "items": [], "count": 0 }`。修改绑定时再次调用上面的
绑定接口即可；服务端按 `company_id + assistant_id + knowledge_base_id` 更新原记录。

## 6. 数据源管理接口

数据源用于描述文件、数据库或外部 API 的来源。当前接口只保存配置和绑定关系，
同步文档导入仍使用第 7 节的原始文件接口。数据库密码、Token、API Key 不能写入 `config`
或 `sync_config`，只能由服务端密钥管理系统提供 `credentials_ref`。

### 创建数据源

`POST /api/rag/admin/data-sources`

```json
{
  "company_id": "16",
  "user_id": "863",
  "source_key": "hr-policy-files",
  "name": "人事制度文件",
  "source_type": "file",
  "config": {
    "storage": "local"
  },
  "credentials_ref": "",
  "sync_config": {
    "allowed_extensions": [".pdf", ".docx", ".txt"]
  }
}
```

`source_type` 可选：`file`、`database`、`api`。创建成功返回 `201` 和 `item`。

数据库数据源示例只能保存非敏感连接信息：

```json
{
  "source_key": "erp-readonly",
  "name": "ERP 只读库",
  "source_type": "database",
  "config": {
    "host": "db.internal",
    "port": 3306,
    "database": "erp",
    "tables": ["hr_policy"]
  },
  "credentials_ref": "vault://erp/read-only",
  "sync_config": {
    "max_rows": 10000
  }
}
```

### 查询数据源

`POST /api/rag/admin/data-sources/list`

```json
{
  "company_id": "16",
  "user_id": "863",
  "status": "active"
}
```

响应为 `{ "items": [], "count": 0 }`，`status` 可选 `active`、`disabled`、`archived`。

### 编辑或停用数据源

`POST /api/rag/admin/data-sources/{data_source_id}/update`

```json
{
  "company_id": "16",
  "user_id": "863",
  "name": "ERP 只读数据源",
  "status": "disabled",
  "config": {
    "host": "db.internal",
    "port": 3306,
    "database": "erp"
  },
  "credentials_ref": "vault://erp/read-only",
  "sync_config": {
    "max_rows": 5000
  }
}
```

以上字段均可选，但至少提交一个。`source_key`、`source_type` 创建后不可修改；需要切换
来源类型时应新建数据源。`config` 和 `sync_config` 仍禁止保存密码、Token 或 API Key，
传空对象或空字符串可清除对应配置。

### 绑定知识库和数据源

`POST /api/rag/admin/bindings/knowledge-base-source`

```json
{
  "company_id": "16",
  "user_id": "863",
  "knowledge_base_id": 10,
  "data_source_id": 20,
  "enabled": true,
  "priority": 0,
  "import_config": {
    "chunk_size": 800
  }
}
```

当前绑定接口用于保存平台配置；真正从数据库/API 数据源自动同步到 Milvus 的任务接口
尚未启用，前端不要把它显示为“已完成同步”。

查询绑定：`POST /api/rag/admin/bindings/knowledge-base-source/list`

```json
{
  "company_id": "16",
  "user_id": "863",
  "knowledge_base_id": 10,
  "data_source_id": 20,
  "enabled": true
}
```

三个过滤字段均可省略，响应为 `{ "items": [], "count": 0 }`。修改绑定仍调用上面的绑定
接口，服务端按 `company_id + knowledge_base_id + data_source_id` 更新原记录。

## 7. 文档导入接口

导入接口是同步接口：请求返回前会完成解析、切分、Embedding 和 Milvus upsert。单文件
最大 `20MB`，不需要 `python-multipart`。

### 通用文档导入

`POST /api/rag/ingest/document`

请求体是原始文件，参数使用 Query：

```text
/api/rag/ingest/document
  ?company_id=16
  &user_id=863
  &knowledge_base_key=employee_handbook
  &source=员工手册.docx
  &title=员工手册
  &version=2026
  &effective_date=2026-01-01
  &department=公共制度
  &permission_tags=hr,manager
  &chunk_size=800
  &chunk_overlap=120
```

支持的 `source` 后缀：

```text
.pdf .docx .txt .md .markdown .json .csv .xml .html .htm
```

PowerShell 示例：

```powershell
$headers = @{ UID = "863"; Authorization = "Bearer xxx" }
Invoke-RestMethod -Method Post `
  "http://127.0.0.1:8021/api/rag/ingest/document?company_id=16&user_id=863&knowledge_base_key=employee_handbook&source=employee-handbook.docx&version=2026" `
  -Headers $headers `
  -ContentType "application/vnd.openxmlformats-officedocument.wordprocessingml.document" `
  -InFile .\employee-handbook.docx
```

浏览器 `fetch` 示例：

```js
async function ingestDocument(file, knowledgeBaseKey) {
  const params = new URLSearchParams({
    company_id: currentUser.companyId,
    user_id: currentUser.userId,
    knowledge_base_key: knowledgeBaseKey,
    source: file.name,
  });

  const response = await fetch(
    `${API_BASE_URL}/api/rag/ingest/document?${params}`,
    {
      method: "POST",
      headers: {
        UID: currentUser.uid,
        Authorization: currentUser.authorization,
        "Content-Type": file.type || "application/octet-stream",
      },
      body: file,
    },
  );
  const payload = await response.json();
  if (!response.ok) {
    const error = new Error(payload.detail?.message || payload.detail || "文档导入失败");
    error.detail = payload.detail;
    throw error;
  }
  return payload;
}
```

响应：

```json
{
  "status": "completed",
  "source": "employee-handbook.docx",
  "chunk_count": 23,
  "inserted_count": 23,
  "empty_pages": [],
  "company_id": "16",
  "knowledge_base_key": "employee_handbook",
  "collection": "erp_knowledge_chunks_v2",
  "job_id": 101,
  "job_key": "7b02bd7e9a7145bba4d66f8b221f619e"
}
```

`chunk_size`、`chunk_overlap` 不传时使用知识库后台配置；没有知识库配置时使用项目默认值。
扫描版 PDF 没有文字层时会返回 `422`，当前接口不会自动 OCR。
同一知识库中再次导入相同的 `source + version` 时，新 Chunk 成功写入后会清理旧 Chunk，
因此修改文档后重新上传不会继续检索到已经删除的旧段落。
`version` 可以留空；此时空字符串作为一个独立的“未版本化”分组，只会替换同一 `source`
且同样未填写版本的旧 Chunk，不会影响其他版本。
通用文档的 `permission_tags` 使用逗号分隔，必须是当前 ERP 用户已拥有权限的子集；最多
32 个标签、单个标签最多 256 个字符，超限或越权分别返回 `422`/`403`。
配置 MySQL 且指定已创建的 `knowledge_base_key` 时，响应会同时返回 `job_id` 和 `job_key`；
未配置 MySQL 时两者为空，但同步导入本身仍可使用。

### 文本导入

`POST /api/rag/ingest/text`

请求体为 JSON：

```json
{
  "content": "需要入库的制度正文",
  "user_id": "863",
  "company_id": "16",
  "knowledge_base_key": "employee_handbook",
  "source": "manual.txt",
  "title": "员工制度",
  "department": "公共制度",
  "version": "2026",
  "effective_date": "2026-01-01",
  "permission_tags": ["hr"],
  "chunk_size": 800,
  "chunk_overlap": 120
}
```

`chunk_size` 和 `chunk_overlap` 可以省略；省略时优先使用知识库管理配置，未配置知识库时
使用 `.env` 中的 `RAG_CHUNK_SIZE`、`RAG_CHUNK_OVERLAP`。请求体中的 `department` 会被
ERP 返回的真实部门覆盖。`permission_tags` 会写入文档 ACL，必须是当前 ERP 用户已拥有的
权限标签子集，否则返回 `403`，不能通过上传参数给文档扩大可见范围；最多 32 个标签，
单个标签最多 256 个字符。

响应格式与通用文档导入相同。

### PDF 导入

`POST /api/rag/ingest/pdf`

请求体是原始 PDF，必须使用：

```http
Content-Type: application/pdf
```

`company_id`、`user_id`、`source`、`knowledge_base_key` 等使用 Query 参数。响应格式与
通用文档导入相同。`permission_tags` 也是可选 Query 参数，使用逗号分隔；每个标签都必须
属于当前 ERP 用户已拥有的权限，否则返回 `403`。最多 32 个标签、单个标签最多 256 个
字符；不传标签表示公共 ACL 文档。

例如：

```text
/api/rag/ingest/pdf
  ?company_id=16
  &user_id=863
  &knowledge_base_key=employee_handbook
  &source=员工手册.pdf
  &version=2026
  &permission_tags=hr,manager
```

### 查询导入状态

`POST /api/rag/ingest/jobs/status`

```json
{
  "company_id": "16",
  "user_id": "863",
  "knowledge_base_key": "employee_handbook",
  "job_id": 101
}
```

```json
{
  "id": 101,
  "job_key": "7b02bd7e9a7145bba4d66f8b221f619e",
  "status": "failed",
  "document_id": 55,
  "document_status": "failed",
  "source": "employee-handbook.docx",
  "knowledge_base_key": "employee_handbook",
  "total_pages": 18,
  "parsed_pages": 18,
  "chunk_count": 23,
  "inserted_chunk_count": 0,
  "error_code": "embedding_or_milvus_failed",
  "error_message": "Milvus 写入失败：...",
  "retryable": true
}
```

状态依次为 `pending`、`parsing`、`embedding`、`completed` 或 `failed`。接口仍按
`company_id + knowledge_base_key + ERP 写入权限` 校验，不能查询其他租户或无权知识库的任务。

### 重试失败导入

`POST /api/rag/ingest/jobs/retry`

请求体与状态查询相同。只有 `failed` 且服务端源文件仍可用的任务能重试；服务端会创建
新的任务记录，保留旧失败任务用于审计。成功响应与文档导入一致，并返回新的
`job_id/job_key`。重试不需要浏览器重新上传文件；服务端会按当前 ERP 用户权限重新校验
历史文档 ACL，且在 ACL 校验通过前不会创建新的任务记录；用户权限被收回时重试会返回
`403`，原失败任务仍可由有权限的管理员继续补偿。

跟踪开启时，导入失败的 HTTP `detail` 是对象而不是字符串：

```json
{
  "detail": {
    "message": "Milvus 写入失败：...",
    "status": "failed",
    "retryable": true,
    "job_id": 101,
    "job_key": "7b02bd7e9a7145bba4d66f8b221f619e"
  }
}
```

### 文档列表

`POST /api/rag/documents/list`

```json
{
  "company_id": "16",
  "user_id": "863",
  "knowledge_base_key": "employee_handbook",
  "keyword": "员工手册",
  "page": 1,
  "page_size": 20
}
```

响应中的文档由 Milvus Chunk 按 `source + version` 聚合：

```json
{
  "items": [
    {
      "source": "employee-handbook.docx",
      "title": "员工手册",
      "version": "2026",
      "effective_date": "2026-01-01",
      "department": "公共制度",
      "permission_tags": ["knowledge:employee_handbook"],
      "chunk_count": 23,
      "page_count": 18
    }
  ],
  "count": 1,
  "total": 1,
  "page": 1,
  "page_size": 20,
  "company_id": "16",
  "knowledge_base_key": "employee_handbook",
  "collection": "erp_knowledge_chunks_v2"
}
```

### 删除文档

`POST /api/rag/documents/delete`

必须同时传入精确的 `source` 和 `version`，避免误删同名的其他版本：

```json
{
  "company_id": "16",
  "user_id": "863",
  "knowledge_base_key": "employee_handbook",
  "source": "employee-handbook.docx",
  "version": "2026"
}
```

```json
{
  "status": "deleted",
  "source": "employee-handbook.docx",
  "version": "2026",
  "deleted_chunk_count": 23,
  "company_id": "16",
  "knowledge_base_key": "employee_handbook",
  "collection": "erp_knowledge_chunks_v2"
}
```

文档不存在或当前 ERP 用户无权访问时返回 `404`。删除成功后对应 Chunk 不再参与检索。

## 8. 搜索接口

### `POST /api/rag/search`

请求体：

```json
{
  "query": "病假需要什么材料？",
  "user_id": "863",
  "company_id": "16",
  "assistant_key": "employee-rag",
  "knowledge_base_key": "employee_handbook",
  "top_k": 5
}
```

响应：

```json
{
  "evidence": [
    {
      "chunk_id": "16:employee_handbook:...",
      "text": "病假申请需要提交就医材料。",
      "source": "employee-handbook.docx",
      "page": 9,
      "title": "病假管理",
      "company_id": "16",
      "department": "公共制度",
      "version": "2026",
      "effective_date": "2026-01-01",
      "is_active": true,
      "permission_tags": ["hr"],
      "score": 0.86,
      "retrieval_rank": 3,
      "rerank_score": 0.96,
      "rank": 1
    }
  ],
  "citations": [
    {
      "citation_id": 1,
      "chunk_id": "16:employee_handbook:...",
      "source": "employee-handbook.docx",
      "title": "病假管理",
      "page": 9,
      "score": 0.96,
      "snippet": "病假申请需要提交就医材料。"
    }
  ],
  "count": 1,
  "company_id": "16",
  "knowledge_base_key": "employee_handbook",
  "collection": "erp_knowledge_chunks_v2"
}
```

前端引用列表直接使用 `citations`；`chunk_id` 只用于原文定位，不作为展示文案。
`score` 是向量相似度，`rerank_score` 是 LLM 重排相关度，`rank` 是最终顺序。
`top_k` 范围为 `1..50`，未传时使用知识库或服务默认值。重排失败时服务端自动回退到
向量顺序，此时不会提供 `rerank_score`。

## 9. LLM 问答接口

### `POST /api/rag/chat`

请求体与搜索基本相同，增加可选的 `system_context`：

```json
{
  "query": "病假需要什么材料？",
  "user_id": "863",
  "company_id": "16",
  "assistant_key": "employee-rag",
  "knowledge_base_key": "employee_handbook",
  "top_k": 5,
  "system_context": "请用简洁、正式的中文回答。"
}
```

服务端先执行向量搜索，再将检索证据交给真实 LLM。已发布的
`knowledge_answer/primary` Prompt 和 Assistant 模型配置会自动合并使用，Prompt 的模型
参数优先于 Assistant 配置。

响应：

```json
{
  "message": "根据员工手册，病假申请需要提交就医材料。\n\n依据：[1]《employee-handbook.docx》第 9 页",
  "evidence": [
    {
      "source": "employee-handbook.docx",
      "page": 9,
      "score": 0.86
    }
  ],
  "citations": [
    {
      "citation_id": 1,
      "chunk_id": "16:employee_handbook:...",
      "source": "employee-handbook.docx",
      "title": "病假管理",
      "page": 9,
      "score": 0.96,
      "snippet": "病假申请需要提交就医材料。"
    }
  ],
  "count": 1,
  "company_id": "16",
  "knowledge_base_key": "employee_handbook",
  "collection": "erp_knowledge_chunks_v2"
}
```

`message` 是最终答案，`evidence` 与搜索接口结构相同，`citations` 用于前端来源区。
没有检索到证据时服务端直接返回“未检索到与当前问题匹配的知识库依据，暂时无法确认答案”，
不会让 LLM 凭常识补写答案；前端应把它当作无答案状态展示，并提供重新提问或切换知识库的入口。

问答的固定数据流是：ERP 身份校验 → 知识库/Assistant 权限校验 → Milvus 向量召回 → 可选
LLM Rerank → 仅基于证据生成答案 → 服务端追加可信引用。LLM 只能处理已过滤的证据，不能
绕过 `company_id`、部门或权限标签隔离。

## 10. 会话接口（可选）

只有 `AI_ERP_SESSION_STORE=mysql` 启用后，下面两个接口才会读取长期会话；默认内存模式
下会返回 `503`。会话始终按 `company_id + assistant_key + ERP 用户` 隔离。

### 会话列表

`POST /api/sessions/list`

```json
{
  "company_id": "16",
  "user_id": "863",
  "assistant_key": "employee-rag",
  "status": "active",
  "page": 1,
  "page_size": 20
}
```

响应：

```json
{
  "items": [
    {
      "session_id": "rag-session-001",
      "title": "员工病假制度",
      "status": "active",
      "workflow_status": "idle",
      "last_message_seq": 4,
      "last_active_at": "2026-08-31T10:00:00"
    }
  ],
  "count": 1,
  "page": 1,
  "page_size": 20,
  "has_more": false
}
```

### 会话消息

`POST /api/sessions/messages`

```json
{
  "company_id": "16",
  "user_id": "863",
  "assistant_key": "employee-rag",
  "session_id": "rag-session-001",
  "before_seq": null,
  "page_size": 50
}
```

响应中的 `items` 按聊天显示顺序返回，每条消息包含 `message_seq`、`request_id`、`role`、
`content`、`route`、`status` 和 `created_at`。向上翻页时，把响应中的
`next_before_seq` 作为下一次请求的 `before_seq`。

## 11. 错误处理

统一错误响应通常为字符串；可重试导入失败时 `detail` 为上一节所示对象：

```json
{
  "detail": "错误说明"
}
```

常见状态码：

| 状态码 | 含义 | 前端处理建议 |
|---|---|---|
| `401` | ERP 身份校验失败 | 重新获取登录凭据 |
| `403` | 公司、部门或权限标签不满足知识库策略，或上传文档 ACL 超出当前用户权限 | 禁止继续提交，检查登录态、文档标签和管理员配置 |
| `404` | Assistant、知识库或 Prompt 配置不存在 | 提示管理员完成配置 |
| `409` | 业务标识或版本重复 | 刷新列表，避免重复提交 |
| `415` | PDF 请求未使用 `application/pdf` | 修正上传 Content-Type |
| `422` | 参数、文件格式或 Chunk 配置错误 | 展示 `detail` 并允许用户修改 |
| `503` | MySQL、Embedding、Milvus、Collection 或 LLM 当前不可用 | 展示稍后重试，不要自动无限重试 |

## 12. 前端状态建议

文档导入按钮至少维护以下状态：

```text
idle -> uploading -> parsing -> embedding -> completed
                                      \-> failed
```

接口仍同步等待处理完成；配置 MySQL 后可使用返回的 `job_id` 查询失败阶段并触发补偿，
但它不是后台轮询任务。前端在原请求期间显示“处理中”，失败后再显示“重试”操作。

问答页面建议保存：

```text
assistant_key
knowledge_base_key
query
message
evidence
citations
```

`company_id`、`UID`、`Authorization` 来自当前 ERP 登录态，不要让用户在普通页面手工编辑。

## 13. 当前限制

- 不支持扫描 PDF OCR。
- 配置 MySQL 且指定知识库时，同步导入会写文档和任务状态；未配置时不提供状态查询与服务端重试。
- 文档列表暂由 Milvus Chunk 聚合；单个 Collection 超过 `16384` 个可见 Chunk 后应改为 MySQL 文档记录分页。
- `permission_tags` 是文档 ACL 元数据；检索使用 ERP 验证后的 `permissions/roles`，请求体中的标签不会被当作可信用户权限。
- 不支持通过浏览器直接提交任意 SQL；数据库数据源目前只有管理配置接口。
- 单文件最大 `20MB`。

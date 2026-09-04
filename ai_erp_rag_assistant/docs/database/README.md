# 数据库设计

当前按执行顺序提供三组 MySQL 8.0+ 建表草案，以及两组已建表环境补充 SQL：

- `001_mysql8_assistant_config.sql`：公司级 Assistant、配置版本、Prompt、禁用词、知识库、文档和入库任务。
- `002_mysql8_sessions.sql`：关联 Assistant 和配置版本的长期会话与消息历史。
- `003_mysql8_approval_audit.sql`：审批草稿、冻结预览、提交幂等和工具调用审计。
- `004_mysql8_rag_unified_search.sql`：旧版本已经创建 001 表时补充文件检索开关、向量版本和公司级检索范围字段。
- `005_mysql8_assistant_retrieval_targets.sql`：已经创建 001 与 004 表时补充 Assistant 配置版本的指定知识库数组。
- `006_approval_assistant_seed.sql`：为已有公司补充固定 `approval-assistant` 系统 Assistant 行；不新增表。

全新环境直接执行当前版本的 `001`、`002`、`003`；当前 `001` 已包含统一检索范围和
指定知识库数组字段，不要再重复执行 `004`、`005`。只有已经按旧版本建过表的环境，才按实际
缺失字段选择执行 `004`、`005`，执行前必须由数据库管理员核对字段和约束是否存在。

应用不会自动执行这些 SQL，也不会调用 `Base.metadata.create_all()`；具体环境是否已建表以人工执行结果为准。

## 关键约束

- 所有租户业务表都包含 `company_id`，复合外键同时校验公司和业务对象。
- 一个公司可以建立多个 Assistant，每个 Assistant 可以发布独立配置和 Prompt。
- Prompt 使用 `prompt_key + variant + version` 管理主版本、副版本、发布与归档。
- Assistant 只保存全局 Prompt、模型和检索默认参数；知识库启用后自动进入公司级检索，旧的
  `ai_erp_assistant_knowledge_bases` 绑定表仅作为兼容数据保留，不再是检索前置条件。
- Assistant 配置版本的 `retrieval_scope=selected` 必须保存至少一个
  `knowledge_base_keys_json`；应用层同时校验这些 Key 属于当前公司且知识库处于 active，
  `company_enabled` 模式则要求该字段为空。增量环境的旧兼容版本暂不追加 JSON CHECK，
  由应用层拒绝新的无效配置，避免历史兼容数据阻断补充字段。
- 文档通过 `search_enabled` 独立控制是否参与检索，只有 `status=published` 且开关为 1 的文件可见。
  该筛选组合有对应复合索引，避免公司级全库检索随着停用文件增加而退化为全表扫描。
- PDF 文件只保存元数据和对象存储地址，向量仍进入 Milvus。
- 会话唯一键为 `company_id + assistant_id + user_id + session_key`。
- 消息使用 `message_seq` 保证会话内顺序。
- `request_id` 用于前端重试幂等；为空时允许普通历史消息写入。
- `state_version` 用于后续条件更新，防止多个服务实例覆盖彼此状态。
- 不保存 Authorization、API Key、Cookie、刷新令牌或密码。
- 所有应用时间按 UTC 写入，展示时再转换时区。

## 应用接入

同步 RAG 导入已接入 `ai_erp_knowledge_documents` 和
`ai_erp_knowledge_ingest_jobs`，记录源文件、解析/Embedding/Milvus 阶段、计数和失败原因；
失败重试创建新任务并保留旧任务审计。数据库/API 数据源的自动同步任务仍未接入。

应用层已接入 MySQL 长期会话，并按以下四张表落库：

1. `ai_erp_approval_drafts` 保存可恢复的审批字段和自选审批人。
2. `ai_erp_approval_previews` 保存不可变预览快照和版本哈希。
3. `ai_erp_submission_attempts` 保存提交幂等、超时和核对结果。
4. `ai_erp_tool_events` 保存脱敏后的 ERP/RAG/LLM 工具事件。

设置 `AI_ERP_SESSION_STORE=mysql` 后启用 RAG 会话。审批助手还要求每个公司按 `006` 配置
`approval-assistant` 系统 Assistant 行，配置完成后同样写入上述会话表；未配置时审批仍可用，
但会话历史保持进程内状态并在接口中返回 `persistence_status=not_configured`。启用时还必须配置
`AI_ERP_MYSQL_HOST`、`AI_ERP_MYSQL_PORT`、`AI_ERP_MYSQL_DATABASE`、`AI_ERP_MYSQL_USER`
和 `AI_ERP_MYSQL_PASSWORD`。数据库不可用或配置缺失时，聊天和会话读取接口返回 `503`，不会
静默回退到内存（审批助手在系统行尚未配置时除外），避免审批重试时重复提交。建表和迁移仍必须由人工在明确的目标环境单独执行，
应用不会自动建表。

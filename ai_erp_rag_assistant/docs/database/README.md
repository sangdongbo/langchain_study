# 数据库设计

当前按执行顺序提供三组 MySQL 8.0+ 建表草案：

- `001_mysql8_assistant_config.sql`：公司级 Assistant、配置版本、Prompt、禁用词、知识库、文档和入库任务。
- `002_mysql8_sessions.sql`：关联 Assistant 和配置版本的长期会话与消息历史。
- `003_mysql8_approval_audit.sql`：审批草稿、冻结预览、提交幂等和工具调用审计。

应用不会自动执行这些 SQL，也不会调用 `Base.metadata.create_all()`；具体环境是否已建表以人工执行结果为准。

## 关键约束

- 所有租户业务表都包含 `company_id`，复合外键同时校验公司和业务对象。
- 一个公司可以建立多个 Assistant，每个 Assistant 可以发布独立配置和 Prompt。
- Prompt 使用 `prompt_key + variant + version` 管理主版本、副版本、发布与归档。
- Assistant 与知识库为多对多关系，检索参数可以按绑定关系覆盖。
- PDF 文件只保存元数据和对象存储地址，向量仍进入 Milvus。
- 会话唯一键为 `company_id + assistant_id + user_id + session_key`。
- 消息使用 `message_seq` 保证会话内顺序。
- `request_id` 用于前端重试幂等；为空时允许普通历史消息写入。
- `state_version` 用于后续条件更新，防止多个服务实例覆盖彼此状态。
- 不保存 Authorization、API Key、Cookie、刷新令牌或密码。
- 所有应用时间按 UTC 写入，展示时再转换时区。

## 应用接入

应用层已接入 MySQL 长期会话，并按以下四张表落库：

1. `ai_erp_approval_drafts` 保存可恢复的审批字段和自选审批人。
2. `ai_erp_approval_previews` 保存不可变预览快照和版本哈希。
3. `ai_erp_submission_attempts` 保存提交幂等、超时和核对结果。
4. `ai_erp_tool_events` 保存脱敏后的 ERP/RAG/LLM 工具事件。

设置 `AI_ERP_SESSION_STORE=mysql` 后启用；未启用时使用进程内会话。建表和迁移仍必须
由人工在明确的目标环境单独执行，应用不会自动建表。

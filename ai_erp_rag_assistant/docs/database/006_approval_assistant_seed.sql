-- 审批助手会话持久化的系统 Assistant 初始化示例。
-- 本文件只供 DBA 审核，不由应用自动执行；请将占位符替换为真实租户和操作人。
-- 现有表已包含在 001_mysql8_assistant_config.sql，无需新增表。

INSERT INTO `ai_erp_assistants` (
    `company_id`, `assistant_key`, `name`, `status`, `created_by`
) VALUES (
    '<COMPANY_ID>', 'approval-assistant', '审批助手', 'active', '<OPERATOR_UID>'
)
ON DUPLICATE KEY UPDATE
    `name` = VALUES(`name`),
    `status` = 'active',
    `updated_at` = CURRENT_TIMESTAMP(6);

-- 说明：
-- 1. 每个 ERP 公司执行一次；不要为每个用户重复插入。
-- 2. 不需要创建配置版本，审批助手的流程和字段来自 ERP 实时接口。
-- 3. 执行后 /api/chat、/api/sessions/list、/api/sessions/messages 才会为审批助手使用 MySQL。

-- 已执行 001 与 004 表结构时使用的非破坏性补充 SQL（MySQL 8.0.16+）。
-- 本文件只增加配置版本字段，不执行删除、清空、迁移或数据刷新。
-- 执行前请由数据库管理员确认字段及约束尚不存在，并在维护窗口执行。

ALTER TABLE `ai_erp_assistant_config_versions`
    ADD COLUMN `knowledge_base_keys_json` JSON NULL
        COMMENT 'selected 模式的默认知识库 Key 数组；company_enabled 时为空'
        AFTER `retrieval_scope`;

-- Key 是否属于当前 company_id 且处于 active 状态由应用层事务校验，
-- 因为 MySQL CHECK 约束不能安全引用另一张租户业务表。
-- 增量环境不追加 selected 的 CHECK，避免旧的兼容配置（尚未保存数组）阻断迁移；
-- 新建环境使用 001 中的完整 CHECK，所有新版本仍由应用层强制至少选择一个 Key。

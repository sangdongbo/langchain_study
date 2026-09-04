-- 已创建 001 表结构时使用的非破坏性补充 SQL（MySQL 8.0.16+）。
-- 本文件只增加字段和约束，不执行删除、清空、迁移或数据刷新。
-- 执行前请由数据库管理员确认字段尚不存在，并在维护窗口执行。
-- 全新环境当前 001 已包含 retrieval_scope，请勿在全新 001 后重复执行本文件。

ALTER TABLE `ai_erp_assistant_config_versions`
    ADD COLUMN `retrieval_scope` VARCHAR(24) NOT NULL DEFAULT 'company_enabled'
        COMMENT '检索范围：公司内全部启用知识库或显式指定知识库' AFTER `retrieval_config_json`;

ALTER TABLE `ai_erp_knowledge_documents`
    ADD COLUMN `search_enabled` TINYINT(1) NOT NULL DEFAULT 1
        COMMENT '文件是否参与公司级检索：1启用，0停用' AFTER `status`,
    ADD COLUMN `vector_version` VARCHAR(128) NULL
        COMMENT '写入 Milvus 的来源版本字符串；与内部版本号分开保存' AFTER `search_enabled`;

ALTER TABLE `ai_erp_assistant_config_versions`
    ADD CONSTRAINT `chk_ai_erp_config_retrieval_scope`
        CHECK (`retrieval_scope` IN ('company_enabled', 'selected'));

ALTER TABLE `ai_erp_knowledge_documents`
    ADD CONSTRAINT `chk_ai_erp_document_search_enabled`
        CHECK (`search_enabled` IN (0, 1));

ALTER TABLE `ai_erp_knowledge_documents`
    ADD INDEX `idx_ai_erp_document_search_scope`
        (`company_id`, `knowledge_base_id`, `status`, `search_enabled`, `updated_at`);

-- 说明：ai_erp_assistant_knowledge_bases 仍保留给旧页面和历史数据，
-- 新的公司级检索不会再读取它作为准入条件，也不要求前端建立绑定。
-- Assistant 在配置页选择具体知识库的数组字段见 005_mysql8_assistant_retrieval_targets.sql。

-- Long-term company- and assistant-scoped sessions (MySQL 8.0.16+)
-- Requires 001_mysql8_assistant_config.sql. Review before execution.

CREATE TABLE `ai_erp_sessions` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '会话主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '处理该会话的助手ID',
    `config_version_id` BIGINT UNSIGNED NULL COMMENT '会话当前使用的助手配置版本ID',
    `session_key` VARCHAR(128) NOT NULL COMMENT '前端会话标识，在公司、助手和用户范围内唯一',
    `user_id` VARCHAR(64) NOT NULL COMMENT '系统用户ID',
    `erp_uid` VARCHAR(64) NULL COMMENT '调用ERP接口使用的UID，仅保存标识不保存令牌',
    `title` VARCHAR(255) NULL COMMENT '会话标题',
    `status` VARCHAR(32) NOT NULL DEFAULT 'active' COMMENT '会话状态：active、archived或deleted',
    `current_route` VARCHAR(32) NULL COMMENT '最近一次消息命中的工作流路由',
    `workflow_status` VARCHAR(32) NOT NULL DEFAULT 'idle' COMMENT '当前工作流状态，如waiting_user或preview_ready',
    `active_approval` TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否存在进行中的审批草稿',
    `state_version` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '会话状态乐观锁版本号',
    `state_json` JSON NULL COMMENT '可恢复的脱敏工作流状态，不得包含Authorization或其他凭证',
    `summary_text` TEXT NULL COMMENT '用于压缩长期上下文的会话摘要',
    `summary_version` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '会话摘要版本号',
    `last_message_seq` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '会话内最后分配的消息序号',
    `last_active_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '最近活跃时间',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间，应用按UTC写入',
    `archived_at` DATETIME(6) NULL COMMENT '归档时间',
    `deleted_at` DATETIME(6) NULL COMMENT '逻辑删除时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_sessions_owner_key` (`company_id`, `assistant_id`, `user_id`, `session_key`),
    UNIQUE KEY `uk_ai_erp_sessions_company_assistant_id` (`company_id`, `assistant_id`, `id`),
    KEY `idx_ai_erp_sessions_owner_active` (`company_id`, `assistant_id`, `user_id`, `last_active_at`),
    KEY `idx_ai_erp_sessions_workflow` (`company_id`, `assistant_id`, `workflow_status`, `updated_at`),
    KEY `idx_ai_erp_sessions_config` (`company_id`, `assistant_id`, `config_version_id`),
    CONSTRAINT `chk_ai_erp_sessions_status`
        CHECK (`status` IN ('active', 'archived', 'deleted')),
    CONSTRAINT `chk_ai_erp_sessions_approval`
        CHECK (`active_approval` IN (0, 1)),
    CONSTRAINT `fk_ai_erp_sessions_assistant`
        FOREIGN KEY (`company_id`, `assistant_id`)
        REFERENCES `ai_erp_assistants` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT `fk_ai_erp_sessions_config`
        FOREIGN KEY (`company_id`, `assistant_id`, `config_version_id`)
        REFERENCES `ai_erp_assistant_config_versions` (`company_id`, `assistant_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='AI ERP assistant sessions; never stores Authorization tokens';

CREATE TABLE `ai_erp_messages` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '消息主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '生成或处理该消息的助手ID',
    `session_id` BIGINT UNSIGNED NOT NULL COMMENT '所属会话ID',
    `config_version_id` BIGINT UNSIGNED NULL COMMENT '处理该消息时使用的助手配置版本ID',
    `message_seq` BIGINT UNSIGNED NOT NULL COMMENT '会话内单调递增的消息序号',
    `request_id` VARCHAR(64) NULL COMMENT '前端生成的请求幂等标识',
    `role` VARCHAR(16) NOT NULL COMMENT '消息角色：user、assistant、system或tool',
    `content` MEDIUMTEXT NOT NULL COMMENT '消息正文',
    `route` VARCHAR(32) NULL COMMENT '该消息命中的工作流路由',
    `status` VARCHAR(24) NOT NULL DEFAULT 'completed' COMMENT '消息处理状态：processing、completed或failed',
    `model_name` VARCHAR(128) NULL COMMENT '生成该消息时使用的模型名称',
    `prompt_snapshot_json` JSON NULL COMMENT '生成该消息时使用的Prompt键及版本快照',
    `metadata_json` JSON NULL COMMENT '脱敏后的扩展元数据，不得包含凭证或原始令牌',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '消息创建时间，应用按UTC写入',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_messages_session_seq` (`session_id`, `message_seq`),
    UNIQUE KEY `uk_ai_erp_messages_session_request` (`session_id`, `request_id`),
    UNIQUE KEY `uk_ai_erp_messages_company_assistant_session_id` (`company_id`, `assistant_id`, `session_id`, `id`),
    KEY `idx_ai_erp_messages_session_created` (`company_id`, `assistant_id`, `session_id`, `created_at`),
    KEY `idx_ai_erp_messages_config` (`company_id`, `assistant_id`, `config_version_id`),
    CONSTRAINT `chk_ai_erp_messages_role`
        CHECK (`role` IN ('user', 'assistant', 'system', 'tool')),
    CONSTRAINT `chk_ai_erp_messages_status`
        CHECK (`status` IN ('processing', 'completed', 'failed')),
    CONSTRAINT `fk_ai_erp_messages_session`
        FOREIGN KEY (`company_id`, `assistant_id`, `session_id`)
        REFERENCES `ai_erp_sessions` (`company_id`, `assistant_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT `fk_ai_erp_messages_config`
        FOREIGN KEY (`company_id`, `assistant_id`, `config_version_id`)
        REFERENCES `ai_erp_assistant_config_versions` (`company_id`, `assistant_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Immutable AI ERP conversation messages with redacted runtime snapshots';

CREATE TABLE `ai_erp_message_citations` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '回答引用主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '助手ID',
    `session_id` BIGINT UNSIGNED NOT NULL COMMENT '会话ID',
    `message_id` BIGINT UNSIGNED NOT NULL COMMENT '产生引用的消息ID',
    `knowledge_base_id` BIGINT UNSIGNED NOT NULL COMMENT '召回知识库ID',
    `document_id` BIGINT UNSIGNED NOT NULL COMMENT '召回文档ID',
    `document_version` INT UNSIGNED NOT NULL COMMENT '召回文档版本',
    `chunk_id` VARCHAR(128) NOT NULL COMMENT 'Milvus中的Chunk标识',
    `rank` INT UNSIGNED NOT NULL COMMENT '召回排序，从1开始',
    `score` DECIMAL(10,8) NULL COMMENT '召回或重排得分',
    `title_snapshot` VARCHAR(255) NULL COMMENT '回答时的文档标题快照',
    `content_hash` CHAR(64) NULL COMMENT '回答时引用内容的SHA-256摘要',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '引用创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_citation_message_rank` (`message_id`, `rank`),
    KEY `idx_ai_erp_citation_message` (`company_id`, `assistant_id`, `session_id`, `message_id`),
    KEY `idx_ai_erp_citation_document` (`company_id`, `knowledge_base_id`, `document_id`),
    CONSTRAINT `chk_ai_erp_citation_rank`
        CHECK (`rank` > 0),
    CONSTRAINT `fk_ai_erp_citation_message`
        FOREIGN KEY (`company_id`, `assistant_id`, `session_id`, `message_id`)
        REFERENCES `ai_erp_messages` (`company_id`, `assistant_id`, `session_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT `fk_ai_erp_citation_document`
        FOREIGN KEY (`company_id`, `knowledge_base_id`, `document_id`, `document_version`)
        REFERENCES `ai_erp_knowledge_documents` (`company_id`, `knowledge_base_id`, `id`, `version`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Auditable RAG citations attached to assistant messages';

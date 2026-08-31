-- AI ERP RAG Assistant 审批草稿、预览、提交幂等和工具审计表。
-- 仅供审查，禁止直接在生产库执行；按 001、002 的顺序执行后再执行本文件。

CREATE TABLE `ai_erp_approval_drafts` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '审批草稿主键',
    `company_id` VARCHAR(64) NOT NULL COMMENT '公司租户ID',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '所属助手ID',
    `session_id` BIGINT UNSIGNED NOT NULL COMMENT '所属长期会话ID',
    `user_id` VARCHAR(128) NOT NULL COMMENT '发起用户业务ID',
    `draft_key` VARCHAR(128) NOT NULL COMMENT '客户端或服务端草稿幂等键',
    `template_id` VARCHAR(128) NOT NULL COMMENT 'ERP审批模板ID',
    `template_title` VARCHAR(255) NOT NULL DEFAULT '' COMMENT '审批模板名称快照',
    `workflow_status` VARCHAR(32) NOT NULL DEFAULT 'collecting_fields' COMMENT '草稿状态：collecting_fields、waiting_user、preview_ready、waiting_assignee、waiting_erp、submitted、cancelled、blocked或failed',
    `fields_json` JSON NOT NULL COMMENT '当前已采集字段值；仅用于恢复流程，不作为日志明文',
    `selected_assignees_json` JSON NOT NULL COMMENT '发起人自选审批人，按节点ID保存',
    `state_version` INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '草稿乐观锁版本',
    `last_error_code` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最近一次错误代码',
    `last_error_message` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '最近一次错误摘要',
    `expires_at` DATETIME(6) NULL COMMENT '草稿过期时间',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（UTC）',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_draft_key` (`company_id`, `assistant_id`, `draft_key`),
    UNIQUE KEY `uk_ai_erp_draft_company_session_id` (`company_id`, `assistant_id`, `id`),
    KEY `idx_ai_erp_draft_session_status` (`company_id`, `assistant_id`, `session_id`, `workflow_status`, `updated_at`),
    KEY `idx_ai_erp_draft_expire` (`company_id`, `expires_at`),
    CONSTRAINT `fk_ai_erp_draft_assistant` FOREIGN KEY (`company_id`, `assistant_id`)
        REFERENCES `ai_erp_assistants` (`company_id`, `id`),
    CONSTRAINT `fk_ai_erp_draft_session` FOREIGN KEY (`company_id`, `assistant_id`, `session_id`)
        REFERENCES `ai_erp_sessions` (`company_id`, `assistant_id`, `id`),
    CONSTRAINT `chk_ai_erp_draft_status` CHECK (`workflow_status` IN ('collecting_fields','waiting_user','preview_ready','waiting_assignee','waiting_erp','submitted','cancelled','blocked','failed'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='AI审批长期草稿';

CREATE TABLE `ai_erp_approval_previews` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '审批预览主键',
    `company_id` VARCHAR(64) NOT NULL COMMENT '公司租户ID',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '所属助手ID',
    `draft_id` BIGINT UNSIGNED NOT NULL COMMENT '所属审批草稿ID',
    `preview_id` CHAR(32) NOT NULL COMMENT '预览公开ID',
    `preview_version` INT UNSIGNED NOT NULL COMMENT '同一草稿内的预览版本',
    `preview_hash` CHAR(64) NOT NULL COMMENT '模板、字段、节点快照哈希',
    `template_id` VARCHAR(128) NOT NULL COMMENT 'ERP审批模板ID快照',
    `submission_fields_json` JSON NOT NULL COMMENT '提交前ERP字段结构快照',
    `nodes_json` JSON NOT NULL COMMENT 'ERP审批节点原始快照',
    `submit_nodes_json` JSON NOT NULL COMMENT '应用自选审批人后的提交节点快照',
    `approval_flow_json` JSON NOT NULL COMMENT '前端可渲染的审批流程快照',
    `requires_confirmation` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否仍需要用户确认',
    `confirmation_status` VARCHAR(32) NOT NULL DEFAULT 'pending' COMMENT '确认状态：pending、confirmed、rejected、consumed、write_disabled',
    `idempotency_key` VARCHAR(128) NOT NULL COMMENT '审批提交幂等键',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（UTC）',
    `consumed_at` DATETIME(6) NULL COMMENT '预览被提交或关闭时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_preview_public_id` (`company_id`, `assistant_id`, `preview_id`),
    UNIQUE KEY `uk_ai_erp_preview_version` (`company_id`, `assistant_id`, `draft_id`, `preview_version`),
    UNIQUE KEY `uk_ai_erp_preview_hash` (`company_id`, `assistant_id`, `draft_id`, `preview_hash`),
    KEY `idx_ai_erp_preview_draft` (`company_id`, `assistant_id`, `draft_id`, `created_at`),
    CONSTRAINT `fk_ai_erp_preview_draft` FOREIGN KEY (`company_id`, `assistant_id`, `draft_id`)
        REFERENCES `ai_erp_approval_drafts` (`company_id`, `assistant_id`, `id`),
    CONSTRAINT `chk_ai_erp_preview_confirm` CHECK (`confirmation_status` IN ('pending','confirmed','rejected','consumed','write_disabled'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='AI审批冻结预览';

CREATE TABLE `ai_erp_submission_attempts` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '提交尝试主键',
    `company_id` VARCHAR(64) NOT NULL COMMENT '公司租户ID',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '所属助手ID',
    `session_id` BIGINT UNSIGNED NOT NULL COMMENT '所属长期会话ID',
    `draft_id` BIGINT UNSIGNED NULL COMMENT '关联审批草稿ID',
    `preview_id` CHAR(32) NULL COMMENT '关联预览ID',
    `idempotency_key` VARCHAR(128) NOT NULL COMMENT '提交幂等键',
    `template_id` VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'ERP审批模板ID',
    `request_id` VARCHAR(128) NOT NULL DEFAULT '' COMMENT 'ERP请求或审批单ID',
    `attempt_no` INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '同一幂等键的尝试次数',
    `status` VARCHAR(32) NOT NULL COMMENT 'started、succeeded、failed、timeout、reconciled、blocked',
    `erp_mode` VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'ERP读取模式快照',
    `erp_write_mode` VARCHAR(16) NOT NULL DEFAULT '' COMMENT 'ERP写入模式快照',
    `http_status` SMALLINT UNSIGNED NULL COMMENT 'ERP HTTP状态码',
    `error_code` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '错误代码',
    `error_message` VARCHAR(500) NOT NULL DEFAULT '' COMMENT '错误摘要',
    `response_summary_json` JSON NULL COMMENT '脱敏后的ERP响应摘要',
    `started_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '开始时间（UTC）',
    `finished_at` DATETIME(6) NULL COMMENT '结束时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_submission_idempotency` (`company_id`, `assistant_id`, `idempotency_key`),
    KEY `idx_ai_erp_submission_session` (`company_id`, `assistant_id`, `session_id`, `started_at`),
    KEY `idx_ai_erp_submission_request` (`company_id`, `request_id`),
    CONSTRAINT `fk_ai_erp_submission_assistant` FOREIGN KEY (`company_id`, `assistant_id`)
        REFERENCES `ai_erp_assistants` (`company_id`, `id`),
    CONSTRAINT `fk_ai_erp_submission_session` FOREIGN KEY (`company_id`, `assistant_id`, `session_id`)
        REFERENCES `ai_erp_sessions` (`company_id`, `assistant_id`, `id`),
    CONSTRAINT `fk_ai_erp_submission_draft` FOREIGN KEY (`company_id`, `assistant_id`, `draft_id`)
        REFERENCES `ai_erp_approval_drafts` (`company_id`, `assistant_id`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='AI审批提交尝试和幂等记录';

CREATE TABLE `ai_erp_tool_events` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '工具事件主键',
    `company_id` VARCHAR(64) NOT NULL COMMENT '公司租户ID',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '所属助手ID',
    `session_id` BIGINT UNSIGNED NULL COMMENT '所属长期会话ID',
    `message_id` BIGINT UNSIGNED NULL COMMENT '关联消息ID',
    `request_id` VARCHAR(128) NOT NULL DEFAULT '' COMMENT '调用请求ID',
    `event_id` CHAR(32) NOT NULL COMMENT '事件唯一ID',
    `tool_name` VARCHAR(128) NOT NULL COMMENT '工具名称，例如 erp.approval.add',
    `event_type` VARCHAR(32) NOT NULL COMMENT 'request、response、timing、error、decision',
    `success` TINYINT(1) NULL COMMENT '是否成功',
    `duration_ms` INT UNSIGNED NULL COMMENT '耗时毫秒',
    `payload_summary_json` JSON NOT NULL COMMENT '脱敏后的事件摘要，不保存令牌和表单值',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_tool_event_id` (`company_id`, `assistant_id`, `event_id`),
    KEY `idx_ai_erp_tool_session_time` (`company_id`, `assistant_id`, `session_id`, `created_at`),
    KEY `idx_ai_erp_tool_request` (`company_id`, `request_id`),
    KEY `idx_ai_erp_tool_name_time` (`company_id`, `tool_name`, `created_at`),
    CONSTRAINT `fk_ai_erp_tool_assistant` FOREIGN KEY (`company_id`, `assistant_id`)
        REFERENCES `ai_erp_assistants` (`company_id`, `id`),
    CONSTRAINT `fk_ai_erp_tool_session` FOREIGN KEY (`company_id`, `assistant_id`, `session_id`)
        REFERENCES `ai_erp_sessions` (`company_id`, `assistant_id`, `id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci COMMENT='AI工具调用与审批审计事件';

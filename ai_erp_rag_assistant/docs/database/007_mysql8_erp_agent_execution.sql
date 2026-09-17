-- ERP Agent Durable Execution 运行、步骤和检查点表（MySQL 8.0.16+）。
-- 依赖 001_mysql8_assistant_config.sql；仅供人工审查，本文件不包含 DROP/TRUNCATE。

CREATE TABLE `ai_erp_agent_runs` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '运行主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '执行本次运行的助手ID',
    `run_key` CHAR(32) NOT NULL COMMENT '对外公开的运行ID',
    `session_key` VARCHAR(128) NOT NULL COMMENT '前端会话标识',
    `user_id` VARCHAR(64) NOT NULL COMMENT '已验证的ERP用户ID',
    `request_id` VARCHAR(64) NOT NULL COMMENT '前端请求幂等标识',
    `request_hash` CHAR(64) NOT NULL COMMENT '不含凭据的业务输入SHA-256摘要',
    `status` VARCHAR(24) NOT NULL DEFAULT 'running' COMMENT '运行状态：running、completed或failed',
    `current_step` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最近开始或完成的步骤名',
    `state_json` JSON NULL COMMENT '最后一个脱敏检查点状态，不得包含Token或Cookie',
    `result_json` JSON NULL COMMENT '完成后的权威ChatResponse，用于幂等返回',
    `state_version` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '检查点单调版本号',
    `retry_count` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '失败或租约过期后的恢复次数',
    `owner_token` CHAR(32) NULL COMMENT '当前执行进程持有的随机租约令牌',
    `lease_expires_at` DATETIME(6) NULL COMMENT '运行租约到期时间（UTC）',
    `last_error_code` VARCHAR(64) NOT NULL DEFAULT '' COMMENT '最近错误代码',
    `last_error_message` VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '最近错误摘要',
    `started_at` DATETIME(6) NULL COMMENT '首次开始时间（UTC）',
    `completed_at` DATETIME(6) NULL COMMENT '完成时间（UTC）',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（UTC）',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_agent_run_key` (`run_key`),
    UNIQUE KEY `uk_ai_erp_agent_run_request` (`company_id`, `assistant_id`, `request_id`),
    UNIQUE KEY `uk_ai_erp_agent_run_company_assistant_id` (`company_id`, `assistant_id`, `id`),
    KEY `idx_ai_erp_agent_run_owner` (`company_id`, `assistant_id`, `user_id`, `created_at`),
    KEY `idx_ai_erp_agent_run_status` (`company_id`, `assistant_id`, `status`, `updated_at`),
    KEY `idx_ai_erp_agent_run_lease` (`status`, `lease_expires_at`),
    CONSTRAINT `chk_ai_erp_agent_run_status`
        CHECK (`status` IN ('running', 'completed', 'failed')),
    CONSTRAINT `fk_ai_erp_agent_run_assistant`
        FOREIGN KEY (`company_id`, `assistant_id`)
        REFERENCES `ai_erp_assistants` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='ERP Agent可恢复运行及租约';

CREATE TABLE `ai_erp_agent_steps` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '步骤主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '所属助手ID',
    `run_id` BIGINT UNSIGNED NOT NULL COMMENT '所属运行ID',
    `step_name` VARCHAR(64) NOT NULL COMMENT '稳定步骤名',
    `status` VARCHAR(24) NOT NULL DEFAULT 'running' COMMENT '步骤状态：running、completed或failed',
    `attempt_count` INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '本步骤实际尝试次数',
    `replayable` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '完成后恢复时是否复用输出',
    `input_json` JSON NULL COMMENT '执行前的脱敏输入快照',
    `output_json` JSON NULL COMMENT '执行成功后的脱敏节点输出',
    `error_message` VARCHAR(1000) NOT NULL DEFAULT '' COMMENT '最近错误摘要',
    `started_at` DATETIME(6) NULL COMMENT '最近一次开始时间（UTC）',
    `finished_at` DATETIME(6) NULL COMMENT '最近一次结束时间（UTC）',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（UTC）',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '更新时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_agent_step` (`run_id`, `step_name`),
    KEY `idx_ai_erp_agent_step_status` (`company_id`, `assistant_id`, `status`, `updated_at`),
    CONSTRAINT `chk_ai_erp_agent_step_status`
        CHECK (`status` IN ('running', 'completed', 'failed')),
    CONSTRAINT `chk_ai_erp_agent_step_replayable`
        CHECK (`replayable` IN (0, 1)),
    CONSTRAINT `fk_ai_erp_agent_step_run`
        FOREIGN KEY (`company_id`, `assistant_id`, `run_id`)
        REFERENCES `ai_erp_agent_runs` (`company_id`, `assistant_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='ERP Agent节点执行和重试记录';

CREATE TABLE `ai_erp_agent_checkpoints` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '检查点主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '所属助手ID',
    `run_id` BIGINT UNSIGNED NOT NULL COMMENT '所属运行ID',
    `checkpoint_seq` BIGINT UNSIGNED NOT NULL COMMENT '运行内单调递增的检查点序号',
    `step_name` VARCHAR(64) NOT NULL COMMENT '产生检查点的步骤名',
    `phase` VARCHAR(24) NOT NULL COMMENT '检查点阶段：before_step、after_step或failed',
    `state_json` JSON NOT NULL COMMENT '可恢复的脱敏状态快照',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间（UTC）',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_agent_checkpoint_seq` (`run_id`, `checkpoint_seq`),
    KEY `idx_ai_erp_agent_checkpoint_step` (`company_id`, `assistant_id`, `run_id`, `step_name`, `created_at`),
    CONSTRAINT `chk_ai_erp_agent_checkpoint_phase`
        CHECK (`phase` IN ('before_step', 'after_step', 'failed')),
    CONSTRAINT `fk_ai_erp_agent_checkpoint_run`
        FOREIGN KEY (`company_id`, `assistant_id`, `run_id`)
        REFERENCES `ai_erp_agent_runs` (`company_id`, `assistant_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='ERP Agent节点前后不可变检查点';

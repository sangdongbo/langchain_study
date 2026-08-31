-- Company-scoped assistant, prompt and knowledge-base configuration (MySQL 8.0.16+)
-- Review before execution. This file intentionally contains no DROP/TRUNCATE.

CREATE TABLE `ai_erp_assistants` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '助手主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_key` VARCHAR(64) NOT NULL COMMENT '公司内唯一的助手业务标识',
    `name` VARCHAR(64) NOT NULL COMMENT '助手名称',
    `status` VARCHAR(24) NOT NULL DEFAULT 'active' COMMENT '助手状态：active、disabled或archived',
    `published_config_version_id` BIGINT UNSIGNED NULL COMMENT '当前已发布的配置版本ID',
    `created_by` VARCHAR(64) NULL COMMENT '创建人用户ID',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间，应用按UTC写入',
    `deleted_at` DATETIME(6) NULL COMMENT '逻辑删除时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_assistants_company_key` (`company_id`, `assistant_key`),
    UNIQUE KEY `uk_ai_erp_assistants_company_id` (`company_id`, `id`),
    KEY `idx_ai_erp_assistants_company_status` (`company_id`, `status`),
    CONSTRAINT `chk_ai_erp_assistants_status`
        CHECK (`status` IN ('active', 'disabled', 'archived'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Company-scoped AI assistant identities';

CREATE TABLE `ai_erp_assistant_config_versions` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '助手配置版本主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '所属助手ID',
    `version` INT UNSIGNED NOT NULL COMMENT '配置版本号，从1递增',
    `status` VARCHAR(24) NOT NULL DEFAULT 'draft' COMMENT '配置状态：draft、published或archived',
    `published_slot` TINYINT GENERATED ALWAYS AS (
        CASE WHEN `status` = 'published' THEN 1 ELSE NULL END
    ) STORED COMMENT '用于约束同一助手只能有一个已发布配置',
    `page_config_json` JSON NULL COMMENT '页面配置：头像、颜色、标题和开场介绍等',
    `model_config_json` JSON NULL COMMENT '模型与回答配置，不得保存API密钥',
    `retrieval_config_json` JSON NULL COMMENT '检索配置：top_k、相关度阈值和重排等',
    `feature_flags_json` JSON NULL COMMENT '历史记录、注册访问、下载和多版本等功能开关',
    `config_hash` CHAR(64) NOT NULL COMMENT '规范化配置内容的SHA-256摘要',
    `created_by` VARCHAR(64) NULL COMMENT '创建人用户ID',
    `published_by` VARCHAR(64) NULL COMMENT '发布人用户ID',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `published_at` DATETIME(6) NULL COMMENT '发布时间',
    `archived_at` DATETIME(6) NULL COMMENT '归档时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_config_version` (`company_id`, `assistant_id`, `version`),
    UNIQUE KEY `uk_ai_erp_config_company_assistant_id` (`company_id`, `assistant_id`, `id`),
    UNIQUE KEY `uk_ai_erp_config_single_published` (`company_id`, `assistant_id`, `published_slot`),
    KEY `idx_ai_erp_config_published` (`company_id`, `assistant_id`, `status`, `published_at`),
    CONSTRAINT `chk_ai_erp_config_status`
        CHECK (`status` IN ('draft', 'published', 'archived')),
    CONSTRAINT `fk_ai_erp_config_assistant`
        FOREIGN KEY (`company_id`, `assistant_id`)
        REFERENCES `ai_erp_assistants` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Versioned page, model, retrieval and feature configuration';

ALTER TABLE `ai_erp_assistants`
    ADD CONSTRAINT `fk_ai_erp_assistant_published_config`
        FOREIGN KEY (`company_id`, `id`, `published_config_version_id`)
        REFERENCES `ai_erp_assistant_config_versions` (`company_id`, `assistant_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT;

CREATE TABLE `ai_erp_prompt_versions` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT 'Prompt版本主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '所属助手ID',
    `prompt_key` VARCHAR(64) NOT NULL COMMENT 'Prompt用途，如router、planner或knowledge_answer',
    `variant` VARCHAR(16) NOT NULL DEFAULT 'primary' COMMENT 'Prompt变体：primary主版本或secondary副版本',
    `version` INT UNSIGNED NOT NULL COMMENT '同一Prompt用途和变体下的版本号',
    `status` VARCHAR(24) NOT NULL DEFAULT 'draft' COMMENT 'Prompt状态：draft、published或archived',
    `published_slot` TINYINT GENERATED ALWAYS AS (
        CASE WHEN `status` = 'published' THEN 1 ELSE NULL END
    ) STORED COMMENT '用于约束同一Prompt用途和变体只能有一个已发布版本',
    `content` MEDIUMTEXT NOT NULL COMMENT 'Prompt正文',
    `content_hash` CHAR(64) NOT NULL COMMENT 'Prompt正文的SHA-256摘要',
    `model_overrides_json` JSON NULL COMMENT '该Prompt专用的模型参数覆盖配置',
    `created_by` VARCHAR(64) NULL COMMENT '创建人用户ID',
    `published_by` VARCHAR(64) NULL COMMENT '发布人用户ID',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `published_at` DATETIME(6) NULL COMMENT '发布时间',
    `archived_at` DATETIME(6) NULL COMMENT '归档时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_prompt_version` (`company_id`, `assistant_id`, `prompt_key`, `variant`, `version`),
    UNIQUE KEY `uk_ai_erp_prompt_single_published` (`company_id`, `assistant_id`, `prompt_key`, `variant`, `published_slot`),
    KEY `idx_ai_erp_prompt_runtime` (`company_id`, `assistant_id`, `prompt_key`, `status`, `published_at`),
    CONSTRAINT `chk_ai_erp_prompt_variant`
        CHECK (`variant` IN ('primary', 'secondary')),
    CONSTRAINT `chk_ai_erp_prompt_status`
        CHECK (`status` IN ('draft', 'published', 'archived')),
    CONSTRAINT `fk_ai_erp_prompt_assistant`
        FOREIGN KEY (`company_id`, `assistant_id`)
        REFERENCES `ai_erp_assistants` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Versioned company-specific prompts and primary/secondary variants';

CREATE TABLE `ai_erp_blocked_terms` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '禁用词主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '所属助手ID',
    `term` VARCHAR(255) NOT NULL COMMENT '需要拦截的关键词或表达式',
    `match_type` VARCHAR(16) NOT NULL DEFAULT 'contains' COMMENT '匹配方式：contains、exact或regex',
    `reply_content` VARCHAR(255) NOT NULL COMMENT '命中禁用词后返回的固定内容',
    `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用：1启用，0停用',
    `sort_order` INT NOT NULL DEFAULT 0 COMMENT '匹配优先级，数值越小越优先',
    `created_by` VARCHAR(64) NULL COMMENT '创建人用户ID',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间，应用按UTC写入',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_blocked_term` (`company_id`, `assistant_id`, `term`, `match_type`),
    KEY `idx_ai_erp_blocked_enabled` (`company_id`, `assistant_id`, `enabled`, `sort_order`),
    CONSTRAINT `chk_ai_erp_blocked_match_type`
        CHECK (`match_type` IN ('contains', 'exact', 'regex')),
    CONSTRAINT `chk_ai_erp_blocked_enabled`
        CHECK (`enabled` IN (0, 1)),
    CONSTRAINT `fk_ai_erp_blocked_assistant`
        FOREIGN KEY (`company_id`, `assistant_id`)
        REFERENCES `ai_erp_assistants` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Company-specific blocked terms and deterministic replies';

CREATE TABLE `ai_erp_knowledge_bases` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '知识库主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `knowledge_key` VARCHAR(64) NOT NULL COMMENT '公司内唯一的知识库业务标识',
    `name` VARCHAR(128) NOT NULL COMMENT '知识库名称',
    `description` TEXT NULL COMMENT '知识库说明',
    `status` VARCHAR(24) NOT NULL DEFAULT 'active' COMMENT '知识库状态：active、disabled或archived',
    `milvus_collection` VARCHAR(128) NOT NULL COMMENT '存储向量的Milvus Collection名称，必须由服务端生成且全局唯一',
    `embedding_provider` VARCHAR(64) NOT NULL COMMENT 'Embedding服务提供方',
    `embedding_model` VARCHAR(128) NOT NULL COMMENT 'Embedding模型名称',
    `embedding_dimension` INT UNSIGNED NOT NULL COMMENT 'Embedding向量维度',
    `chunk_size` INT UNSIGNED NOT NULL DEFAULT 800 COMMENT '文档分块目标字符数',
    `chunk_overlap` INT UNSIGNED NOT NULL DEFAULT 120 COMMENT '相邻分块重叠字符数',
    `default_top_k` SMALLINT UNSIGNED NOT NULL DEFAULT 5 COMMENT '默认返回的检索结果数量',
    `default_score_threshold` DECIMAL(6,5) NOT NULL DEFAULT 0.65000 COMMENT '默认最低相关度阈值',
    `permission_config_json` JSON NULL COMMENT '部门、角色和文档权限等默认过滤配置',
    `version` INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '知识库配置版本号',
    `created_by` VARCHAR(64) NULL COMMENT '创建人用户ID',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间，应用按UTC写入',
    `deleted_at` DATETIME(6) NULL COMMENT '逻辑删除时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_knowledge_company_key` (`company_id`, `knowledge_key`),
    UNIQUE KEY `uk_ai_erp_knowledge_company_id` (`company_id`, `id`),
    UNIQUE KEY `uk_ai_erp_knowledge_milvus_collection` (`milvus_collection`),
    KEY `idx_ai_erp_knowledge_status` (`company_id`, `status`, `updated_at`),
    CONSTRAINT `chk_ai_erp_knowledge_status`
        CHECK (`status` IN ('active', 'disabled', 'archived')),
    CONSTRAINT `chk_ai_erp_knowledge_embedding_dimension`
        CHECK (`embedding_dimension` > 0),
    CONSTRAINT `chk_ai_erp_knowledge_chunking`
        CHECK (`chunk_size` > 0 AND `chunk_overlap` < `chunk_size`),
    CONSTRAINT `chk_ai_erp_knowledge_top_k`
        CHECK (`default_top_k` > 0),
    CONSTRAINT `chk_ai_erp_knowledge_score`
        CHECK (`default_score_threshold` >= 0 AND `default_score_threshold` <= 1)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Company-owned knowledge-base definitions backed by Milvus';

CREATE TABLE `ai_erp_data_sources` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '数据源主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `source_key` VARCHAR(64) NOT NULL COMMENT '公司内唯一的数据源业务标识',
    `name` VARCHAR(128) NOT NULL COMMENT '数据源名称',
    `source_type` VARCHAR(24) NOT NULL COMMENT '数据源类型：file、database或api',
    `status` VARCHAR(24) NOT NULL DEFAULT 'active' COMMENT '数据源状态：active、disabled或archived',
    `config_json` JSON NULL COMMENT '非敏感连接与导入配置；不得保存密码或令牌',
    `credentials_ref` VARCHAR(255) NULL COMMENT '密钥管理系统中的凭据引用，不保存原始凭据',
    `sync_config_json` JSON NULL COMMENT '同步频率、增量字段和查询模板等受控配置',
    `created_by` VARCHAR(64) NULL COMMENT '创建人用户ID',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间，应用按UTC写入',
    `deleted_at` DATETIME(6) NULL COMMENT '逻辑删除时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_data_source_company_key` (`company_id`, `source_key`),
    UNIQUE KEY `uk_ai_erp_data_source_company_id` (`company_id`, `id`),
    KEY `idx_ai_erp_data_source_status` (`company_id`, `status`, `updated_at`),
    CONSTRAINT `chk_ai_erp_data_source_type`
        CHECK (`source_type` IN ('file', 'database', 'api')),
    CONSTRAINT `chk_ai_erp_data_source_status`
        CHECK (`status` IN ('active', 'disabled', 'archived'))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Company-owned RAG import sources; credentials live outside MySQL';

CREATE TABLE `ai_erp_knowledge_base_sources` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '知识库与数据源绑定主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `knowledge_base_id` BIGINT UNSIGNED NOT NULL COMMENT '知识库ID',
    `data_source_id` BIGINT UNSIGNED NOT NULL COMMENT '数据源ID',
    `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用该数据源：1启用，0停用',
    `priority` INT NOT NULL DEFAULT 0 COMMENT '同步优先级，数值越小越优先',
    `import_config_json` JSON NULL COMMENT '该知识库对数据源的表、字段和过滤条件覆盖配置',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间，应用按UTC写入',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_kb_source` (`company_id`, `knowledge_base_id`, `data_source_id`),
    UNIQUE KEY `uk_ai_erp_kb_source_company_id` (`company_id`, `knowledge_base_id`, `id`),
    KEY `idx_ai_erp_kb_source_order` (`company_id`, `knowledge_base_id`, `enabled`, `priority`),
    CONSTRAINT `chk_ai_erp_kb_source_enabled`
        CHECK (`enabled` IN (0, 1)),
    CONSTRAINT `fk_ai_erp_kb_source_knowledge`
        FOREIGN KEY (`company_id`, `knowledge_base_id`)
        REFERENCES `ai_erp_knowledge_bases` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT `fk_ai_erp_kb_source_data_source`
        FOREIGN KEY (`company_id`, `data_source_id`)
        REFERENCES `ai_erp_data_sources` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Company-scoped knowledge-base data-source bindings';

CREATE TABLE `ai_erp_assistant_knowledge_bases` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '助手与知识库绑定主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `assistant_id` BIGINT UNSIGNED NOT NULL COMMENT '助手ID',
    `knowledge_base_id` BIGINT UNSIGNED NOT NULL COMMENT '知识库ID',
    `enabled` TINYINT(1) NOT NULL DEFAULT 1 COMMENT '是否启用该知识库：1启用，0停用',
    `priority` INT NOT NULL DEFAULT 0 COMMENT '知识库检索优先级，数值越小越优先',
    `retrieval_config_json` JSON NULL COMMENT '该助手对知识库的top_k、相关度阈值等覆盖配置',
    `permission_filter_json` JSON NULL COMMENT '该助手访问知识库时附加的权限过滤配置',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间，应用按UTC写入',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_assistant_knowledge` (`company_id`, `assistant_id`, `knowledge_base_id`),
    KEY `idx_ai_erp_assistant_knowledge_order` (`company_id`, `assistant_id`, `enabled`, `priority`),
    CONSTRAINT `chk_ai_erp_assistant_knowledge_enabled`
        CHECK (`enabled` IN (0, 1)),
    CONSTRAINT `fk_ai_erp_assistant_kb_assistant`
        FOREIGN KEY (`company_id`, `assistant_id`)
        REFERENCES `ai_erp_assistants` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT `fk_ai_erp_assistant_kb_knowledge`
        FOREIGN KEY (`company_id`, `knowledge_base_id`)
        REFERENCES `ai_erp_knowledge_bases` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Many-to-many bindings between assistants and knowledge bases';

CREATE TABLE `ai_erp_knowledge_documents` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '知识库文档主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `knowledge_base_id` BIGINT UNSIGNED NOT NULL COMMENT '所属知识库ID',
    `data_source_id` BIGINT UNSIGNED NULL COMMENT '来源数据源ID；上传文件可为空',
    `document_key` VARCHAR(64) NOT NULL COMMENT '同一文档跨版本保持不变的业务标识',
    `source_type` VARCHAR(24) NOT NULL DEFAULT 'upload' COMMENT '内容来源：upload、file、database或api',
    `file_name` VARCHAR(255) NULL COMMENT '上传时的原始文件名；非文件来源为空',
    `title` VARCHAR(255) NULL COMMENT '文档标题',
    `mime_type` VARCHAR(127) NULL COMMENT '文件MIME类型；非文件来源为空',
    `storage_uri` VARCHAR(1024) NULL COMMENT '对象存储或文件服务地址；非文件来源为空',
    `source_record_key` VARCHAR(255) NULL COMMENT '数据库/API记录的稳定业务标识',
    `content_sha256` CHAR(64) NOT NULL COMMENT '原始文件或规范化来源内容的SHA-256摘要',
    `version` INT UNSIGNED NOT NULL DEFAULT 1 COMMENT '同一document_key下的文档版本号',
    `status` VARCHAR(24) NOT NULL DEFAULT 'uploaded' COMMENT '文档状态：uploaded、parsing、embedding、published、failed或expired',
    `effective_at` DATETIME(6) NULL COMMENT '文档生效时间',
    `expired_at` DATETIME(6) NULL COMMENT '文档失效时间',
    `permission_scope_json` JSON NULL COMMENT '文档允许访问的部门、角色或用户范围',
    `page_count` INT UNSIGNED NULL COMMENT '文档总页数',
    `character_count` BIGINT UNSIGNED NULL COMMENT '解析得到的文本字符数',
    `created_by` VARCHAR(64) NULL COMMENT '上传人用户ID',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '创建时间，应用按UTC写入',
    `updated_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) ON UPDATE CURRENT_TIMESTAMP(6) COMMENT '最后更新时间，应用按UTC写入',
    `deleted_at` DATETIME(6) NULL COMMENT '逻辑删除时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_document_version` (`company_id`, `knowledge_base_id`, `document_key`, `version`),
    UNIQUE KEY `uk_ai_erp_document_company_kb_id` (`company_id`, `knowledge_base_id`, `id`),
    UNIQUE KEY `uk_ai_erp_document_company_kb_id_version` (`company_id`, `knowledge_base_id`, `id`, `version`),
    KEY `idx_ai_erp_document_status` (`company_id`, `knowledge_base_id`, `status`, `updated_at`),
    KEY `idx_ai_erp_document_hash` (`company_id`, `knowledge_base_id`, `content_sha256`),
    KEY `idx_ai_erp_document_source_record` (`company_id`, `knowledge_base_id`, `data_source_id`, `source_record_key`),
    CONSTRAINT `chk_ai_erp_document_source_type`
        CHECK (`source_type` IN ('upload', 'file', 'database', 'api')),
    CONSTRAINT `chk_ai_erp_document_source_fields`
        CHECK ((`source_type` = 'upload' AND `data_source_id` IS NULL AND `file_name` IS NOT NULL AND `mime_type` IS NOT NULL AND `storage_uri` IS NOT NULL)
            OR (`source_type` = 'file' AND `data_source_id` IS NOT NULL AND `file_name` IS NOT NULL AND `mime_type` IS NOT NULL AND `storage_uri` IS NOT NULL)
            OR (`source_type` IN ('database', 'api') AND `data_source_id` IS NOT NULL AND `source_record_key` IS NOT NULL)),
    CONSTRAINT `chk_ai_erp_document_status`
        CHECK (`status` IN ('uploaded', 'parsing', 'embedding', 'published', 'failed', 'expired')),
    CONSTRAINT `fk_ai_erp_document_knowledge`
        FOREIGN KEY (`company_id`, `knowledge_base_id`)
        REFERENCES `ai_erp_knowledge_bases` (`company_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT,
    CONSTRAINT `fk_ai_erp_document_source_binding`
        FOREIGN KEY (`company_id`, `knowledge_base_id`, `data_source_id`)
        REFERENCES `ai_erp_knowledge_base_sources` (`company_id`, `knowledge_base_id`, `data_source_id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Versioned document metadata; file contents remain in object storage';

CREATE TABLE `ai_erp_knowledge_ingest_jobs` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '知识库入库任务主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `knowledge_base_id` BIGINT UNSIGNED NOT NULL COMMENT '目标知识库ID',
    `document_id` BIGINT UNSIGNED NOT NULL COMMENT '待解析和入库的文档ID',
    `job_key` VARCHAR(64) NOT NULL COMMENT '公司内唯一的入库任务标识',
    `status` VARCHAR(24) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending、parsing、embedding、completed或failed',
    `parser` VARCHAR(64) NULL COMMENT '使用的文档解析器名称',
    `embedding_model` VARCHAR(128) NULL COMMENT '本次入库使用的Embedding模型',
    `total_pages` INT UNSIGNED NULL COMMENT '待处理总页数',
    `parsed_pages` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已解析页数',
    `chunk_count` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '生成的Chunk总数',
    `inserted_chunk_count` INT UNSIGNED NOT NULL DEFAULT 0 COMMENT '成功写入Milvus的Chunk数量',
    `error_code` VARCHAR(64) NULL COMMENT '失败错误码',
    `error_message` TEXT NULL COMMENT '失败错误信息',
    `started_at` DATETIME(6) NULL COMMENT '任务开始时间',
    `completed_at` DATETIME(6) NULL COMMENT '任务完成时间',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '任务创建时间，应用按UTC写入',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_ingest_job_key` (`company_id`, `job_key`),
    KEY `idx_ai_erp_ingest_document` (`company_id`, `knowledge_base_id`, `document_id`, `created_at`),
    KEY `idx_ai_erp_ingest_status` (`company_id`, `status`, `created_at`),
    CONSTRAINT `chk_ai_erp_ingest_status`
        CHECK (`status` IN ('pending', 'parsing', 'embedding', 'completed', 'failed')),
    CONSTRAINT `fk_ai_erp_ingest_document`
        FOREIGN KEY (`company_id`, `knowledge_base_id`, `document_id`)
        REFERENCES `ai_erp_knowledge_documents` (`company_id`, `knowledge_base_id`, `id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Auditable document parsing, chunking and Milvus ingestion jobs';

CREATE TABLE `ai_erp_data_source_sync_jobs` (
    `id` BIGINT UNSIGNED NOT NULL AUTO_INCREMENT COMMENT '数据源同步任务主键ID',
    `company_id` VARCHAR(64) NOT NULL COMMENT 'ERP公司ID，用于租户隔离',
    `knowledge_base_id` BIGINT UNSIGNED NOT NULL COMMENT '目标知识库ID',
    `data_source_id` BIGINT UNSIGNED NOT NULL COMMENT '待同步的数据源ID',
    `job_key` VARCHAR(64) NOT NULL COMMENT '公司内唯一的同步任务标识',
    `status` VARCHAR(24) NOT NULL DEFAULT 'pending' COMMENT '任务状态：pending、running、completed或failed',
    `cursor_json` JSON NULL COMMENT '增量同步游标，不得包含凭据',
    `total_records` BIGINT UNSIGNED NULL COMMENT '本次发现的记录数',
    `processed_records` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '已处理记录数',
    `created_document_count` BIGINT UNSIGNED NOT NULL DEFAULT 0 COMMENT '创建或更新的文档数',
    `error_code` VARCHAR(64) NULL COMMENT '失败错误码',
    `error_message` TEXT NULL COMMENT '失败错误信息',
    `started_at` DATETIME(6) NULL COMMENT '任务开始时间',
    `completed_at` DATETIME(6) NULL COMMENT '任务完成时间',
    `created_at` DATETIME(6) NOT NULL DEFAULT CURRENT_TIMESTAMP(6) COMMENT '任务创建时间',
    PRIMARY KEY (`id`),
    UNIQUE KEY `uk_ai_erp_source_sync_job_key` (`company_id`, `job_key`),
    KEY `idx_ai_erp_source_sync_status` (`company_id`, `data_source_id`, `status`, `created_at`),
    CONSTRAINT `chk_ai_erp_source_sync_status`
        CHECK (`status` IN ('pending', 'running', 'completed', 'failed')),
    CONSTRAINT `fk_ai_erp_source_sync_binding`
        FOREIGN KEY (`company_id`, `knowledge_base_id`, `data_source_id`)
        REFERENCES `ai_erp_knowledge_base_sources` (`company_id`, `knowledge_base_id`, `data_source_id`)
        ON UPDATE RESTRICT ON DELETE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_0900_ai_ci
  COMMENT='Auditable database/API extraction jobs before document ingestion';

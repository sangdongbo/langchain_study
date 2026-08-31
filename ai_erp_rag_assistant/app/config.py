from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Keep the supported deployment variable names in one place so the example
# template can be checked for drift without loading credentials or services.
SUPPORTED_ENV_KEYS = frozenset(
    {
        "AI_ERP_RAG_HOST",
        "AI_ERP_RAG_PORT",
        "MILVUS_URI",
        "MILVUS_TOKEN",
        "MILVUS_COLLECTION",
        "MILVUS_DIMENSION",
        "RAG_SOURCE_DIR",
        "RAG_PROCESSED_DIR",
        "RAG_CHUNK_SIZE",
        "RAG_CHUNK_OVERLAP",
        "RAG_MIN_SCORE",
        "RAG_COMPANY_ID",
        "RAG_DEPARTMENT",
        "RAG_PERMISSION_TAGS",
        "ERP_MODE",
        "ERP_READ_MODE",
        "ERP_WRITE_MODE",
        "ERP_SKIP_USERINFO_VALIDATION",
        "ERP_BASE_URL",
        "AI_APPROVAL_CRM_BASE_URL",
        "ERP_UID",
        "ERP_AUTHORIZATION",
        "ERP_DEMO_COMPANY_ID",
        "ERP_DEMO_DEPARTMENT",
        "ERP_APPROVAL_LIST_PATH",
        "ERP_FORM_FIELDS_PATH",
        "ERP_GET_NODES_PATH",
        "ERP_ADD_APPROVAL_PATH",
        "ERP_RELATED_LIST_PATH",
        "ERP_HOLIDAY_RULE_PATH",
        "ERP_CALCULATE_HOLIDAY_DURATION_PATH",
        "ERP_USER_LIST_PATH",
        "ERP_USERINFO_PATH",
        "ERP_APPROVAL_STATUS_PATH",
        "LLM_API_KEY",
        "LLM_BASE_URL",
        "LLM_MODEL",
        "LLM_TIMEOUT",
        "DASHSCOPE_API_KEY",
        "DASHSCOPE_BASE_URL",
        "DASHSCOPE_OPENAI_MODEL",
        "DASHSCOPE_EMBEDDING_MODEL",
        "DASHSCOPE_EMBEDDING_DIMENSIONS",
        "DEEPSEEK_API_KEY",
        "DEEPSEEK_BASE_URL",
        "DEEPSEEK_MODEL",
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "EMBEDDING_BASE_URL",
        "EMBEDDING_API_KEY",
        "EMBEDDING_MODEL",
        "EMBEDDING_DIMENSIONS",
        "LANGSMITH_TRACING",
        "LANGSMITH_API_KEY",
        "LANGSMITH_PROJECT",
        "AI_ERP_AUDIT_LOG_PATH",
        "AI_ERP_ASSISTANT_KEY",
        "AI_ERP_SESSION_STORE",
        "AI_ERP_MYSQL_HOST",
        "AI_ERP_MYSQL_PORT",
        "AI_ERP_MYSQL_DATABASE",
        "AI_ERP_MYSQL_USER",
        "AI_ERP_MYSQL_PASSWORD",
        "AI_ERP_MYSQL_CONNECT_TIMEOUT",
    }
)


def _path_from_env(value: str | None, fallback: str) -> Path:
    path = Path(value or fallback)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _bool_from_env(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on", "是"}


class Settings(BaseModel):
    host: str = "127.0.0.1"
    port: int = 8021
    milvus_uri: str = "http://127.0.0.1:19530"
    milvus_token: str = ""
    milvus_collection: str = "erp_knowledge_chunks"
    milvus_dimension: int = Field(default=2048, ge=1)
    rag_source_dir: Path = PROJECT_ROOT / "data" / "knowledge" / "source"
    rag_processed_dir: Path = PROJECT_ROOT / "data" / "knowledge" / "processed"
    rag_chunk_size: int = Field(default=800, ge=100, le=4000)
    rag_chunk_overlap: int = Field(default=120, ge=0, le=1000)
    rag_min_score: float = Field(default=0.35, ge=-1, le=1)
    rag_company_id: str = "lanjing"
    rag_department: str = "公共制度"
    rag_permission_tags: list[str] = Field(default_factory=lambda: ["knowledge:employee_handbook"])
    erp_mode: str = "remote"
    erp_read_mode: str = "remote"
    erp_write_mode: str = "disabled"
    erp_skip_userinfo_validation: bool = False
    erp_base_url: str = "http://127.0.0.1:8002"
    erp_approval_list_path: str = "/api/approval/list"
    erp_form_fields_path: str = "/api/field/formFields"
    erp_get_nodes_path: str = "/api/approval/getNodes"
    erp_add_approval_path: str = "/api/approval/add"
    erp_related_list_path: str = "/api/Company/getRelatedList"
    erp_holiday_rule_path: str = "/api/attendance/getHolidayRuleByUser"
    erp_calculate_holiday_duration_path: str = "/api/attendance/calculateHolidayDuration"
    erp_user_list_path: str = "/api/User/getList"
    erp_userinfo_path: str = "/api/User/userinfo"
    erp_approval_status_path: str = "/api/approval/myList"
    erp_uid: str = ""
    erp_authorization: str = ""
    erp_demo_company_id: str = ""
    erp_demo_department: str = ""
    llm_api_key: str = ""
    llm_base_url: str = ""
    llm_model: str = ""
    llm_timeout: float = 60.0
    langsmith_tracing: bool = False
    langsmith_api_key: str = ""
    langsmith_project: str = "ai-erp-rag-assistant"
    audit_log_path: str = "logs/ai_erp_audit.jsonl"
    assistant_key: str = "erp-rag"
    session_store: str = "memory"
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3306
    mysql_database: str = ""
    mysql_user: str = ""
    mysql_password: str = ""
    mysql_connect_timeout: int = 5
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = Field(default=2048, ge=1)

    @classmethod
    def from_env(cls) -> "Settings":
        # Load repository defaults first, then let process-level variables win.
        # Empty values are ignored so a blank project .env entry cannot mask a
        # usable shared credential from the repository-level file.
        values: dict[str, str] = {}
        for env_path in (PROJECT_ROOT.parent / ".env", PROJECT_ROOT / ".env"):
            for key, value in dotenv_values(env_path).items():
                if value is not None and str(value).strip():
                    values[key] = str(value).strip()
        values.update(
            {
                key: str(value).strip()
                for key, value in os.environ.items()
                if str(value).strip()
            }
        )
        llm_api_key = values.get("LLM_API_KEY") or ""
        llm_base_url = values.get("LLM_BASE_URL") or ""
        llm_model = values.get("LLM_MODEL") or ""
        if not llm_api_key and values.get("DASHSCOPE_BASE_URL") and values.get("DASHSCOPE_API_KEY"):
            llm_api_key = values["DASHSCOPE_API_KEY"]
            llm_base_url = values["DASHSCOPE_BASE_URL"]
            llm_model = values.get("DASHSCOPE_OPENAI_MODEL") or "qwen-plus"
        if not llm_api_key:
            llm_api_key = values.get("DEEPSEEK_API_KEY") or values.get("OPENAI_API_KEY") or ""
            llm_base_url = (
                llm_base_url
                or values.get("DEEPSEEK_BASE_URL")
                or values.get("OPENAI_BASE_URL")
                or "https://api.deepseek.com/v1"
            )
            llm_model = llm_model or values.get("DEEPSEEK_MODEL") or values.get("OPENAI_MODEL") or "deepseek-chat"
        embedding_api_key = (
            values.get("EMBEDDING_API_KEY")
            or values.get("DASHSCOPE_API_KEY")
            or values.get("OPENAI_API_KEY")
            or ""
        )
        embedding_base_url = values.get("EMBEDDING_BASE_URL") or ""
        if not embedding_base_url and values.get("DASHSCOPE_API_KEY"):
            # Workspace keys should use the same OpenAI-compatible endpoint as
            # the configured DashScope LLM; a custom endpoint may be required.
            embedding_base_url = (
                values.get("DASHSCOPE_BASE_URL")
                or "https://dashscope.aliyuncs.com/compatible-mode/v1"
            )
        embedding_model = (
            values.get("EMBEDDING_MODEL")
            or values.get("DASHSCOPE_EMBEDDING_MODEL")
            or "text-embedding-v4"
        )
        return cls(
            host=values.get("AI_ERP_RAG_HOST") or "127.0.0.1",
            port=int(values.get("AI_ERP_RAG_PORT") or 8021),
            milvus_uri=values.get("MILVUS_URI") or "http://127.0.0.1:19530",
            milvus_token=values.get("MILVUS_TOKEN") or "",
            milvus_collection=values.get("MILVUS_COLLECTION") or "erp_knowledge_chunks",
            milvus_dimension=int(values.get("MILVUS_DIMENSION") or values.get("DASHSCOPE_EMBEDDING_DIMENSIONS") or 2048),
            rag_source_dir=_path_from_env(values.get("RAG_SOURCE_DIR"), "data/knowledge/source"),
            rag_processed_dir=_path_from_env(values.get("RAG_PROCESSED_DIR"), "data/knowledge/processed"),
            rag_chunk_size=int(values.get("RAG_CHUNK_SIZE") or 800),
            rag_chunk_overlap=int(values.get("RAG_CHUNK_OVERLAP") or 120),
            rag_min_score=float(values.get("RAG_MIN_SCORE") or 0.35),
            rag_company_id=values.get("RAG_COMPANY_ID") or values.get("ERP_DEMO_COMPANY_ID") or "lanjing",
            rag_department=values.get("RAG_DEPARTMENT") or "公共制度",
            rag_permission_tags=[
                item.strip()
                for item in (values.get("RAG_PERMISSION_TAGS") or "knowledge:employee_handbook").split(",")
                if item.strip()
            ],
            erp_mode=values.get("ERP_MODE") or "remote",
            erp_read_mode=values.get("ERP_READ_MODE") or values.get("ERP_MODE") or "remote",
            erp_write_mode=values.get("ERP_WRITE_MODE") or (
                "mock" if (values.get("ERP_READ_MODE") or values.get("ERP_MODE") or "remote").lower() == "mock" else "disabled"
            ),
            erp_skip_userinfo_validation=_bool_from_env(values.get("ERP_SKIP_USERINFO_VALIDATION")),
            # 兼容其他 ERP 项目使用的变量名；本项目的 ERP_BASE_URL 优先。
            erp_base_url=(
                values.get("ERP_BASE_URL")
                or values.get("AI_APPROVAL_CRM_BASE_URL")
                or "http://127.0.0.1:8002"
            ),
            erp_approval_list_path=values.get("ERP_APPROVAL_LIST_PATH") or "/api/approval/list",
            erp_form_fields_path=values.get("ERP_FORM_FIELDS_PATH") or "/api/field/formFields",
            erp_get_nodes_path=values.get("ERP_GET_NODES_PATH") or "/api/approval/getNodes",
            erp_add_approval_path=values.get("ERP_ADD_APPROVAL_PATH") or "/api/approval/add",
            erp_related_list_path=values.get("ERP_RELATED_LIST_PATH") or "/api/Company/getRelatedList",
            erp_holiday_rule_path=values.get("ERP_HOLIDAY_RULE_PATH") or "/api/attendance/getHolidayRuleByUser",
            erp_calculate_holiday_duration_path=values.get("ERP_CALCULATE_HOLIDAY_DURATION_PATH") or "/api/attendance/calculateHolidayDuration",
            erp_user_list_path=values.get("ERP_USER_LIST_PATH") or "/api/User/getList",
            erp_userinfo_path=values.get("ERP_USERINFO_PATH") or "/api/User/userinfo",
            erp_approval_status_path=values.get("ERP_APPROVAL_STATUS_PATH") or "/api/approval/myList",
            erp_uid=values.get("ERP_UID") or "",
            erp_authorization=values.get("ERP_AUTHORIZATION") or "",
            erp_demo_company_id=values.get("ERP_DEMO_COMPANY_ID") or "",
            erp_demo_department=values.get("ERP_DEMO_DEPARTMENT") or "",
            llm_api_key=llm_api_key,
            llm_base_url=llm_base_url,
            llm_model=llm_model,
            llm_timeout=float(values.get("LLM_TIMEOUT") or 60),
            langsmith_tracing=_bool_from_env(values.get("LANGSMITH_TRACING")),
            langsmith_api_key=values.get("LANGSMITH_API_KEY") or "",
            langsmith_project=values.get("LANGSMITH_PROJECT") or "ai-erp-rag-assistant",
            audit_log_path=values.get("AI_ERP_AUDIT_LOG_PATH") or "logs/ai_erp_audit.jsonl",
            assistant_key=values.get("AI_ERP_ASSISTANT_KEY") or "erp-rag",
            session_store=(values.get("AI_ERP_SESSION_STORE") or "memory").lower(),
            mysql_host=values.get("AI_ERP_MYSQL_HOST") or "127.0.0.1",
            mysql_port=int(values.get("AI_ERP_MYSQL_PORT") or 3306),
            mysql_database=values.get("AI_ERP_MYSQL_DATABASE") or "",
            mysql_user=values.get("AI_ERP_MYSQL_USER") or "",
            mysql_password=values.get("AI_ERP_MYSQL_PASSWORD") or "",
            mysql_connect_timeout=int(values.get("AI_ERP_MYSQL_CONNECT_TIMEOUT") or 5),
            embedding_base_url=embedding_base_url,
            embedding_api_key=embedding_api_key,
            embedding_model=embedding_model,
            embedding_dimensions=int(values.get("DASHSCOPE_EMBEDDING_DIMENSIONS") or values.get("EMBEDDING_DIMENSIONS") or 2048),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()

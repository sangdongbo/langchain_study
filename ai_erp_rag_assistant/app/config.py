from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from dotenv import dotenv_values
from pydantic import BaseModel, Field


PROJECT_ROOT = Path(__file__).resolve().parents[1]


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
    erp_holiday_rule_path: str = "/api/attendance/getHolidayRuleByUser"
    erp_calculate_holiday_duration_path: str = "/api/attendance/calculateHolidayDuration"
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
    embedding_base_url: str = ""
    embedding_api_key: str = ""
    embedding_model: str = ""
    embedding_dimensions: int = Field(default=2048, ge=1)

    @classmethod
    def from_env(cls) -> "Settings":
        # The assistant has its own .env, while model credentials are commonly
        # kept in the repository .env. Empty project values must not mask them.
        values: dict[str, str] = {}
        for env_path in (PROJECT_ROOT.parent / ".env", PROJECT_ROOT / ".env"):
            for key, value in dotenv_values(env_path).items():
                if value is not None and str(value).strip():
                    values[key] = str(value).strip()
        llm_api_key = values.get("LLM_API_KEY") or ""
        llm_base_url = values.get("LLM_BASE_URL") or ""
        llm_model = values.get("LLM_MODEL") or ""
        if not llm_api_key and values.get("DASHSCOPE_BASE_URL") and values.get("DASHSCOPE_API_KEY"):
            llm_api_key = values["DASHSCOPE_API_KEY"]
            llm_base_url = values["DASHSCOPE_BASE_URL"]
            llm_model = values.get("DASHSCOPE_OPENAI_MODEL") or "qwen-plus"
        if not llm_api_key:
            llm_api_key = values.get("DEEPSEEK_API_KEY") or values.get("OPENAI_API_KEY") or ""
            llm_base_url = llm_base_url or values.get("DEEPSEEK_BASE_URL") or "https://api.deepseek.com/v1"
            llm_model = llm_model or values.get("DEEPSEEK_MODEL") or values.get("OPENAI_MODEL") or "deepseek-chat"
        embedding_api_key = (
            values.get("EMBEDDING_API_KEY")
            or values.get("DASHSCOPE_API_KEY")
            or values.get("OPENAI_API_KEY")
            or ""
        )
        embedding_base_url = values.get("EMBEDDING_BASE_URL") or ""
        if not embedding_base_url and values.get("DASHSCOPE_API_KEY"):
            embedding_base_url = "https://dashscope.aliyuncs.com/compatible-mode/v1"
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
            erp_base_url=values.get("ERP_BASE_URL") or "http://127.0.0.1:8002",
            erp_approval_list_path=values.get("ERP_APPROVAL_LIST_PATH") or "/api/approval/list",
            erp_form_fields_path=values.get("ERP_FORM_FIELDS_PATH") or "/api/field/formFields",
            erp_get_nodes_path=values.get("ERP_GET_NODES_PATH") or "/api/approval/getNodes",
            erp_add_approval_path=values.get("ERP_ADD_APPROVAL_PATH") or "/api/approval/add",
            erp_holiday_rule_path=values.get("ERP_HOLIDAY_RULE_PATH") or "/api/attendance/getHolidayRuleByUser",
            erp_calculate_holiday_duration_path=values.get("ERP_CALCULATE_HOLIDAY_DURATION_PATH") or "/api/attendance/calculateHolidayDuration",
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
            embedding_base_url=embedding_base_url,
            embedding_api_key=embedding_api_key,
            embedding_model=embedding_model,
            embedding_dimensions=int(values.get("DASHSCOPE_EMBEDDING_DIMENSIONS") or values.get("EMBEDDING_DIMENSIONS") or 2048),
        )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings.from_env()

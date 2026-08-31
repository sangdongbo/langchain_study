import re
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from ai_erp_rag_assistant.app.api import _rag_runtime_config
from ai_erp_rag_assistant.app.main import app
from ai_erp_rag_assistant.app.models import Base
from ai_erp_rag_assistant.app.rag_admin_api import _knowledge_embedding_config
from ai_erp_rag_assistant.app.rag_admin_repository import RagAdminRepository
from ai_erp_rag_assistant.app.rag_admin_schemas import (
    AssistantConfigCreateRequest,
    DataSourceCreateRequest,
    KnowledgeBaseCreateRequest,
)
from ai_erp_rag_assistant.app.services.milvus_service import MilvusService


def test_rag_models_are_company_scoped_without_schema_side_effects():
    assert len(Base.metadata.tables) == 11
    for table in Base.metadata.tables.values():
        assert "company_id" in table.c
        assert table.c.company_id.nullable is False


def test_admin_config_rejects_inline_credentials():
    with pytest.raises(ValidationError, match="api_key"):
        AssistantConfigCreateRequest(
            company_id="C001",
            model_config={"provider": {"api_key": "secret"}},
        )

    with pytest.raises(ValidationError, match="database_password"):
        DataSourceCreateRequest(
            company_id="C001",
            source_key="erp-db",
            name="ERP 数据库",
            source_type="database",
            config={"host": "db.internal", "auth": {"database_password": "secret"}},
        )


def test_admin_config_keeps_model_config_as_external_json_name():
    request = AssistantConfigCreateRequest(
        company_id="C001",
        model_config={"provider": "openai-compatible"},
    )

    assert request.model_settings == {"provider": "openai-compatible"}
    assert request.model_dump(by_alias=True)["model_config"] == {
        "provider": "openai-compatible"
    }


def test_collection_name_fits_mysql_column_and_milvus_rules():
    request = KnowledgeBaseCreateRequest(
        company_id="C001", knowledge_key="员工制度", name="员工制度"
    )
    name = MilvusService().collection_name(
        company_id="公司" * 64,
        knowledge_base_key=request.knowledge_key * 64,
    )

    assert len(name) <= 128
    assert re.fullmatch(r"[a-zA-Z0-9_]+", name)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("embedding_provider", "other-provider"),
        ("embedding_model", "other-model"),
        ("embedding_dimension", 1),
    ],
)
def test_knowledge_base_rejects_embedding_config_not_used_by_runtime(field, value):
    request = KnowledgeBaseCreateRequest(
        company_id="C001",
        knowledge_key="handbook",
        name="员工制度",
    ).model_copy(update={field: value})

    with pytest.raises(HTTPException) as error:
        _knowledge_embedding_config(request)

    assert error.value.status_code == 422


def test_runtime_config_does_not_require_mysql_when_unconfigured():
    config = _rag_runtime_config(
        None,
        company_id="C001",
        knowledge_base_key="handbook",
        assistant_key="erp-rag",
    )

    assert config.collection == MilvusService().collection_name(
        company_id="C001", knowledge_base_key="handbook"
    )
    assert config.system_context == ""
    assert config.model_overrides is None
    assert config.chunk_size == 800
    assert config.chunk_overlap == 120


def test_runtime_config_merges_published_assistant_and_prompt_model_settings(monkeypatch):
    assistant = SimpleNamespace(
        id=11,
        status="active",
        published_config_version_id=7,
    )
    knowledge_base = SimpleNamespace(
        id=21,
        status="active",
        milvus_collection="c001_handbook",
        chunk_size=800,
        chunk_overlap=120,
        default_top_k=5,
        default_score_threshold=0.65,
    )
    config = SimpleNamespace(
        model_config_json={"model": "qwen-plus", "temperature": 0.2},
    )
    binding = SimpleNamespace(
        retrieval_config_json={"top_k": 8},
    )
    prompt = SimpleNamespace(
        content="使用正式语气",
        model_overrides_json={"temperature": 0.7, "max_tokens": 2048},
    )

    class FakeSession:
        def __init__(self):
            self.rows = iter([config, binding, prompt])

        def scalar(self, _statement):
            return next(self.rows)

    monkeypatch.setattr(
        RagAdminRepository,
        "get_assistant_by_key",
        lambda self, company_id, assistant_key: assistant,
    )
    monkeypatch.setattr(
        RagAdminRepository,
        "get_knowledge_base_by_key",
        lambda self, company_id, knowledge_key: knowledge_base,
    )

    runtime = RagAdminRepository(FakeSession()).runtime_config(
        "C001", "handbook", "erp-rag"
    )

    assert runtime.system_context == "使用正式语气"
    assert runtime.model_overrides == {
        "model": "qwen-plus",
        "temperature": 0.7,
        "max_tokens": 2048,
    }
    assert runtime.chunk_size == 800
    assert runtime.chunk_overlap == 120
    assert runtime.top_k == 8


def test_rag_admin_routes_are_in_openapi_without_opening_database():
    paths = app.openapi()["paths"]

    assert "/api/rag/admin/assistants" in paths
    assert "/api/rag/admin/assistants/{assistant_id}/prompts/{prompt_id}/publish" in paths
    assert "/api/rag/admin/knowledge-bases" in paths
    assert "/api/rag/admin/data-sources" in paths
    assert "/api/rag/ingest/document" in paths
    assert "/api/sessions/list" in paths
    assert "/api/sessions/messages" in paths

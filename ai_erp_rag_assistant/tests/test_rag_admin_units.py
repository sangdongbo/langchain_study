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
    AssistantUpdateRequest,
    DataSourceCreateRequest,
    DataSourceUpdateRequest,
    KnowledgeBaseCreateRequest,
    KnowledgeBaseUpdateRequest,
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


def test_selected_assistant_config_requires_and_normalizes_knowledge_bases():
    request = AssistantConfigCreateRequest(
        company_id="C001",
        retrieval_scope="selected",
        knowledge_base_keys=[" finance-policy ", "finance-policy", "expense-process"],
    )

    assert request.knowledge_base_keys == ["finance-policy", "expense-process"]

    with pytest.raises(ValidationError, match="至少选择一个"):
        AssistantConfigCreateRequest(
            company_id="C001",
            retrieval_scope="selected",
        )

    with pytest.raises(ValidationError, match="不应传"):
        AssistantConfigCreateRequest(
            company_id="C001",
            retrieval_scope="company_enabled",
            knowledge_base_keys=["finance-policy"],
        )


def test_admin_updates_require_a_change_and_keep_secrets_out():
    with pytest.raises(ValidationError, match="至少需要提交一个可修改字段"):
        AssistantUpdateRequest(company_id="C001")

    with pytest.raises(ValidationError, match="api_token"):
        DataSourceUpdateRequest(
            company_id="C001",
            config={"endpoint": "https://example.test", "api_token": "secret"},
        )


def test_knowledge_base_update_validates_partial_chunk_settings(monkeypatch):
    row = SimpleNamespace(chunk_size=800, chunk_overlap=120)

    class FakeSession:
        saved = None

        def add(self, value):
            self.saved = value

        def commit(self):
            pass

    repository = RagAdminRepository(FakeSession())
    monkeypatch.setattr(repository, "get_knowledge_base", lambda company_id, row_id: row)

    with pytest.raises(ValueError, match="chunk_overlap"):
        repository.update_knowledge_base("C001", 21, {"chunk_size": 100})

    updated = repository.update_knowledge_base("C001", 21, {"chunk_overlap": 80})
    assert updated.chunk_overlap == 80

    with pytest.raises(ValidationError, match="chunk_overlap"):
        KnowledgeBaseUpdateRequest(
            company_id="C001", chunk_size=800, chunk_overlap=800
        )


def test_binding_lists_apply_tenant_and_requested_filters():
    statements = []

    class FakeSession:
        def scalars(self, statement):
            statements.append(str(statement))
            return SimpleNamespace(all=lambda: [])

    repository = RagAdminRepository(FakeSession())
    assert repository.list_assistant_knowledge_base_bindings(
        "C001", assistant_id=11, enabled=False
    ) == []
    assert repository.list_knowledge_base_source_bindings(
        "C001", knowledge_base_id=21, data_source_id=31
    ) == []

    assert all("company_id" in statement for statement in statements)
    assert "assistant_id" in statements[0] and "enabled" in statements[0]
    assert "knowledge_base_id" in statements[1] and "data_source_id" in statements[1]


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


def test_runtime_config_defaults_to_all_company_enabled_knowledge_bases():
    knowledge_bases = [
        SimpleNamespace(
            id=21,
            knowledge_key="hr",
            name="员工制度",
            status="active",
            milvus_collection="c001_hr",
            chunk_size=800,
            chunk_overlap=120,
            default_top_k=5,
            default_score_threshold=0.65,
            permission_config_json=None,
        ),
        SimpleNamespace(
            id=22,
            knowledge_key="attendance",
            name="考勤制度",
            status="active",
            milvus_collection="c001_attendance",
            chunk_size=800,
            chunk_overlap=120,
            default_top_k=5,
            default_score_threshold=0.65,
            permission_config_json=None,
        ),
    ]

    class FakeResult:
        def __init__(self, rows):
            self.rows = rows

        def all(self):
            return list(self.rows)

    class FakeSession:
        def __init__(self):
            self.calls = 0

        def scalars(self, _statement):
            self.calls += 1
            return FakeResult(knowledge_bases if self.calls == 1 else [])

    runtime = RagAdminRepository(FakeSession()).runtime_config("C001")

    assert runtime.collection == ""
    assert [target.knowledge_base_key for target in runtime.knowledge_bases] == [
        "hr",
        "attendance",
    ]
    assert all(target.document_scope_loaded for target in runtime.knowledge_bases)


def test_document_search_switch_only_changes_search_flag(monkeypatch):
    document = SimpleNamespace(search_enabled=True)

    class FakeResult:
        def all(self):
            return [document]

    class FakeSession:
        def __init__(self):
            self.committed = False

        def scalars(self, _statement):
            return FakeResult()

        def commit(self):
            self.committed = True

    repository = RagAdminRepository(FakeSession())
    monkeypatch.setattr(
        repository,
        "get_knowledge_base_by_key",
        lambda company_id, knowledge_key: SimpleNamespace(id=21),
    )

    updated = repository.set_document_search_enabled(
        "C001",
        "hr",
        source="policy.pdf",
        version="2026",
        enabled=False,
    )

    assert updated == 1
    assert document.search_enabled is False
    assert repository.session.committed is True


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
        retrieval_scope="selected",
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
    assert runtime.retrieval_scope == "selected"


def test_runtime_config_uses_published_selected_knowledge_base_keys(monkeypatch):
    assistant = SimpleNamespace(id=11, status="active", published_config_version_id=7)
    config = SimpleNamespace(
        model_config_json=None,
        retrieval_config_json=None,
        retrieval_scope="selected",
        knowledge_base_keys_json=["finance", "invoice"],
    )
    knowledge_bases = {
        key: SimpleNamespace(
            id=index,
            knowledge_key=key,
            name=key.title(),
            status="active",
            milvus_collection=f"c001_{key}",
            chunk_size=800,
            chunk_overlap=120,
            default_top_k=5,
            default_score_threshold=0.65,
            permission_config_json=None,
        )
        for index, key in enumerate(("finance", "invoice"), start=21)
    }

    class FakeResult:
        def all(self):
            return []

    class FakeSession:
        def __init__(self):
            self.rows = iter(
                [config, SimpleNamespace(content="", model_overrides_json=None)]
            )

        def scalar(self, _statement):
            return next(self.rows)

        def scalars(self, _statement):
            return FakeResult()

    monkeypatch.setattr(
        RagAdminRepository,
        "get_assistant_by_key",
        lambda self, company_id, assistant_key: assistant,
    )
    monkeypatch.setattr(
        RagAdminRepository,
        "get_knowledge_base_by_key",
        lambda self, company_id, knowledge_key: knowledge_bases[knowledge_key],
    )

    runtime = RagAdminRepository(FakeSession()).runtime_config(
        "C001", assistant_key="finance-assistant"
    )

    assert runtime.retrieval_scope == "selected"
    assert [target.knowledge_base_key for target in runtime.knowledge_bases] == [
        "finance",
        "invoice",
    ]


def test_create_config_persists_selected_knowledge_base_keys(monkeypatch):
    saved = {}

    class FakeSession:
        def scalar(self, _statement):
            return 0

        def add(self, value):
            saved["row"] = value

        def commit(self):
            pass

    repository = RagAdminRepository(FakeSession())
    monkeypatch.setattr(
        repository,
        "get_assistant",
        lambda company_id, assistant_id: SimpleNamespace(id=assistant_id),
    )
    monkeypatch.setattr(
        repository,
        "get_knowledge_base_by_key",
        lambda company_id, knowledge_key: SimpleNamespace(status="active"),
    )

    row = repository.create_config_version(
        "C001",
        11,
        {
            "page_config": {},
            "model_config": {},
            "retrieval_config": {},
            "retrieval_scope": "selected",
            "knowledge_base_keys": ["finance", "invoice"],
            "feature_flags": {},
        },
        "863",
    )

    assert row is saved["row"]
    assert row.knowledge_base_keys_json == ["finance", "invoice"]


def test_rag_admin_routes_are_in_openapi_without_opening_database():
    paths = app.openapi()["paths"]

    assert "/api/rag/admin/assistants" in paths
    assert "/api/rag/admin/assistants/{assistant_id}/update" in paths
    assert "/api/rag/admin/assistants/{assistant_id}/prompts/{prompt_id}/publish" in paths
    assert "/api/rag/admin/knowledge-bases" in paths
    assert "/api/rag/admin/knowledge-bases/{knowledge_base_id}/update" in paths
    assert "/api/rag/admin/data-sources" in paths
    assert "/api/rag/admin/data-sources/{data_source_id}/update" in paths
    assert "/api/rag/admin/bindings/assistant-knowledge-base/list" in paths
    assert "/api/rag/admin/bindings/knowledge-base-source/list" in paths
    assert "/api/rag/ingest/document" in paths
    assert "/api/rag/ingest/jobs/status" in paths
    assert "/api/rag/ingest/jobs/retry" in paths
    assert "/api/rag/documents/list" in paths
    assert "/api/rag/documents/status" in paths
    assert "/api/rag/documents/delete" in paths
    assert "/api/sessions/list" in paths
    assert "/api/sessions/messages" in paths

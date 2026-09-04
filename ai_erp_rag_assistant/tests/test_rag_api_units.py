import json
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ai_erp_rag_assistant.app.api import (
    _persistent_identity,
    _rag_identity,
    _verified_access_tags,
    _rag_rows_from_pdf,
    _rag_rows_from_text,
    rag_chat,
    rag_search,
)
from ai_erp_rag_assistant.app.schemas import (
    RagChatRequest,
    RagSearchRequest,
    RagTextIngestRequest,
    SessionListRequest,
)
from ai_erp_rag_assistant.app.services.milvus_service import MilvusService
from ai_erp_rag_assistant.app.services.model_service import ModelService
from ai_erp_rag_assistant.app.services.ingest_job_service import IngestJobTracker
from ai_erp_rag_assistant.app.routes.rag import (
    _runtime_source_fields,
    _validate_document_permission_tags,
)


def test_collection_name_is_tenant_scoped_and_supports_chinese_keys():
    service = MilvusService()

    first = service.collection_name(company_id="公司甲", knowledge_base_key="员工制度")
    second = service.collection_name(company_id="公司乙", knowledge_base_key="员工制度")

    assert first != second
    assert first == service.collection_name(company_id="公司甲", knowledge_base_key="员工制度")
    assert service.collection_name(company_id="公司甲") == service.settings.milvus_collection


def test_upsert_rejects_chunks_from_another_company_before_external_calls(monkeypatch):
    service = MilvusService()
    monkeypatch.setattr(
        service,
        "ensure_collection",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应连接 Milvus")),
    )

    with pytest.raises(ValueError, match="company_id"):
        service.upsert_chunks(
            [{"text": "制度", "company_id": "C002"}],
            company_id="C001",
            knowledge_base_key="handbook",
        )


def test_text_ingest_rows_keep_tenant_and_knowledge_identity():
    request = RagTextIngestRequest(
        content="第一条制度。第二条制度。第三条制度。",
        company_id="C001",
        knowledge_base_key="handbook",
        source="employee-handbook.txt",
        chunk_size=100,
        chunk_overlap=10,
    )

    rows = _rag_rows_from_text(request)

    assert rows
    assert all(row["company_id"] == "C001" for row in rows)
    assert all(row["chunk_id"].startswith("C001:handbook:") for row in rows)


def test_text_ingest_rejects_invalid_overlap():
    request = RagTextIngestRequest(
        content="制度内容",
        company_id="C001",
        source="policy.txt",
        chunk_size=100,
        chunk_overlap=100,
    )

    with pytest.raises(HTTPException) as error:
        _rag_rows_from_text(request)

    assert error.value.status_code == 422


def test_pdf_rows_keep_page_and_tenant_metadata(monkeypatch):
    pages = [SimpleNamespace(extract_text=lambda: "第一页制度。"), SimpleNamespace(extract_text=lambda: "")]
    monkeypatch.setattr("pypdf.PdfReader", lambda stream: SimpleNamespace(pages=pages))

    rows, empty_pages = _rag_rows_from_pdf(
        b"fake-pdf",
        company_id="C001",
        source="handbook.pdf",
        knowledge_base_key="handbook",
        department="公共制度",
        version="2026",
        effective_date="2026-01-01",
        permission_tags=["hr"],
        chunk_size=100,
        chunk_overlap=10,
    )

    assert rows[0]["page"] == 1
    assert rows[0]["company_id"] == "C001"
    assert rows[0]["permission_tags"] == ["hr"]
    assert empty_pages == [2]


def test_search_api_forwards_tenant_and_knowledge_base(monkeypatch):
    calls = {}

    def fake_search(query, **kwargs):
        calls.update({"query": query, **kwargs})
        return [{"chunk_id": "chunk-1", "score": 0.9}]

    monkeypatch.setattr("ai_erp_rag_assistant.app.api.milvus_service.search", fake_search)
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.model_service.rerank",
        lambda query, evidence, **kwargs: evidence[: kwargs["top_k"]],
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_identity",
        lambda request, authorization, uid: (
            request,
            request.company_id,
            request.department,
            ["knowledge:handbook"],
        ),
    )
    response = rag_search(
        RagSearchRequest(query="病假材料", company_id="C001", knowledge_base_key="handbook"),
        None,
        None,
    )

    assert response.count == 1
    assert calls["company_id"] == "C001"
    assert calls["knowledge_base_key"] == "handbook"


def test_search_api_uses_selected_knowledge_base_array(monkeypatch):
    from ai_erp_rag_assistant.app.rag_admin_repository import (
        RagKnowledgeBaseTarget,
        RagRuntimeConfig,
    )

    calls = {}
    runtime = RagRuntimeConfig(
        collection="",
        top_k=5,
        knowledge_bases=(
            RagKnowledgeBaseTarget(
                knowledge_base_key="finance",
                knowledge_base_name="财务制度库",
                collection="c001_finance",
                document_scope_loaded=True,
            ),
            RagKnowledgeBaseTarget(
                knowledge_base_key="invoice",
                knowledge_base_name="发票管理库",
                collection="c001_invoice",
                document_scope_loaded=True,
            ),
        ),
        retrieval_scope="selected",
    )

    def fake_runtime(*args, **kwargs):
        calls["runtime"] = kwargs
        return runtime

    monkeypatch.setattr("ai_erp_rag_assistant.app.api._rag_runtime_config", fake_runtime)
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.milvus_service.search_many",
        lambda query, **kwargs: [
            {
                "chunk_id": "finance-chunk",
                "knowledge_base_key": "finance",
                "knowledge_base_name": "财务制度库",
                "source": "报销制度.pdf",
                "score": 0.9,
            }
        ],
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_identity",
        lambda request, authorization, uid: (
            request,
            request.company_id,
            request.department,
            [],
        ),
    )

    response = rag_search(
        RagSearchRequest(
            query="住宿费",
            company_id="C001",
            search_scope="selected",
            knowledge_base_keys=["finance", "invoice"],
        ),
        None,
        None,
    )

    assert calls["runtime"]["knowledge_base_keys"] == ["finance", "invoice"]
    assert calls["runtime"]["search_scope"] == "selected"
    assert response.knowledge_base_keys == ["finance", "invoice"]
    assert response.citations[0].knowledge_base_key == "finance"


def test_milvus_search_many_merges_sources_from_enabled_knowledge_bases(monkeypatch):
    service = MilvusService()

    def fake_search(query, **kwargs):
        key = kwargs["knowledge_base_key"]
        return [
            {
                "chunk_id": f"{key}-chunk",
                "source": f"{key}.pdf",
                "score": 0.8 if key == "hr" else 0.9,
            }
        ]

    monkeypatch.setattr(service, "search", fake_search)
    results = service.search_many(
        "病假",
        company_id="C001",
        targets=[
            {
                "knowledge_base_key": "hr",
                "knowledge_base_name": "员工制度",
                "collection": "c001_hr",
            },
            {
                "knowledge_base_key": "attendance",
                "knowledge_base_name": "考勤制度",
                "collection": "c001_attendance",
            },
        ],
        top_k=2,
    )

    assert [item["knowledge_base_key"] for item in results] == ["attendance", "hr"]
    assert results[0]["knowledge_base_name"] == "考勤制度"


def test_milvus_search_many_skips_empty_collection(monkeypatch):
    service = MilvusService()

    def fake_search(query, **kwargs):
        if kwargs["knowledge_base_key"] == "empty":
            raise RuntimeError("Milvus collection 不存在：c001_empty")
        return [{"chunk_id": "live", "score": 0.8}]

    monkeypatch.setattr(service, "search", fake_search)
    results = service.search_many(
        "制度",
        company_id="C001",
        targets=[
            {"knowledge_base_key": "empty", "collection": "c001_empty"},
            {"knowledge_base_key": "live", "collection": "c001_live"},
        ],
    )

    assert [item["knowledge_base_key"] for item in results] == ["live"]


def test_rag_identity_rejects_company_switch(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._erp_user",
        lambda request: {"company_id": "C002", "department": "研发部"},
    )

    with pytest.raises(HTTPException) as error:
        _rag_identity(RagSearchRequest(query="制度", company_id="C001"), None, None)

    assert error.value.status_code == 403


def test_rag_identity_uses_verified_company_when_body_company_is_empty(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._erp_user",
        lambda request: {"company_id": "C001", "department": "研发部"},
    )

    _, company_id, department, _ = _rag_identity(
        RagSearchRequest(query="制度"), None, None
    )

    assert company_id == "C001"
    assert department == "研发部"


def test_runtime_source_fields_hide_knowledge_bases_without_read_permission():
    from ai_erp_rag_assistant.app.rag_admin_repository import (
        RagKnowledgeBaseTarget,
        RagRuntimeConfig,
    )

    runtime = RagRuntimeConfig(
        collection="",
        knowledge_bases=(
            RagKnowledgeBaseTarget(
                knowledge_base_key="finance",
                knowledge_base_name="财务制度",
                collection="c001_finance",
                permission_policies=({"required_tags": ["finance:read"]},),
            ),
            RagKnowledgeBaseTarget(
                knowledge_base_key="hr",
                knowledge_base_name="员工制度",
                collection="c001_hr",
            ),
        ),
    )

    _, keys, names, _, collections = _runtime_source_fields(
        runtime,
        "",
        department="研发部",
        access_tags=["employee"],
    )

    assert keys == ["hr"]
    assert names == [{"knowledge_base_key": "hr", "knowledge_base_name": "员工制度"}]
    assert collections == ["c001_hr"]


def test_rag_identity_uses_verified_permissions_instead_of_request_tags(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._erp_user",
        lambda request: {
            "company_id": "C001",
            "department": "研发部",
            "permissions": ["knowledge:handbook"],
            "roles": "employee",
        },
    )

    _, _, _, access_tags = _rag_identity(
        RagSearchRequest(
            query="制度",
            company_id="C001",
            permission_tags=["forged-admin"],
        ),
        None,
        None,
    )

    assert access_tags == ["employee", "knowledge:handbook"]
    assert "forged-admin" not in access_tags


def test_verified_access_tags_ignore_disabled_permission_map_entries():
    assert _verified_access_tags(
        {
            "permissions": {"employee": True, "admin": False},
            "roles": [{"name": "reviewer", "enabled": True}, {"name": "root", "enabled": False}],
        }
    ) == ["employee", "reviewer"]


def test_rag_identity_does_not_fall_back_to_request_department(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._erp_user",
        lambda request: {"company_id": "C001", "permissions": []},
    )

    _, _, department, _ = _rag_identity(
        RagSearchRequest(query="制度", company_id="C001", department="研发部"),
        None,
        None,
    )

    # ERP 没有可信部门时，Milvus 只能开放公共文档，不能把请求体部门当成授权。
    assert department == ""


def test_document_permission_tags_cannot_exceed_verified_user_tags():
    with pytest.raises(HTTPException) as error:
        _validate_document_permission_tags(["employee", "admin"], ["employee"])

    assert error.value.status_code == 403


def test_document_permission_tags_match_milvus_array_limits():
    with pytest.raises(HTTPException) as error:
        _validate_document_permission_tags([f"tag-{index}" for index in range(33)], [])

    assert error.value.status_code == 422

    with pytest.raises(HTTPException) as error:
        _validate_document_permission_tags(["x" * 257], ["x" * 257])

    assert error.value.status_code == 422


def test_knowledge_answer_without_evidence_abstains_before_llm_call(monkeypatch):
    service = ModelService()
    monkeypatch.setattr(service, "_model", lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("不应调用 LLM")))

    answer = service.answer("未知问题", route="knowledge", evidence=[])

    assert "无法确认答案" in answer


def test_knowledge_answer_replaces_model_citation_with_trusted_citation(monkeypatch):
    service = ModelService()
    monkeypatch.setattr(
        service,
        "_invoke",
        lambda *args, **kwargs: "答案 [99]《错误来源.pdf》第 1 页",
    )

    answer = service.answer(
        "制度问题",
        route="knowledge",
        evidence=[
            {
                "chunk_id": "chunk-1",
                "source": "员工手册.pdf",
                "page": 9,
                "text": "病假材料要求",
            }
        ],
    )

    assert "错误来源.pdf" not in answer
    assert "[1]《员工手册.pdf》第 9 页" in answer


def test_persistent_identity_uses_verified_erp_uid(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._erp_user",
        lambda request: {"company_id": "16", "uid": "", "user_id": request.user_id},
    )

    _, _, company_id, user_id = _persistent_identity(
        SessionListRequest(user_id="untrusted", company_id="16"),
        "Bearer token",
        "863",
    )

    assert company_id == "16"
    assert user_id == "863"


def test_header_identity_overrides_stale_request_body_values():
    from ai_erp_rag_assistant.app.api import _with_header_identity

    request = RagSearchRequest(
        query="制度",
        company_id="C001",
        uid="old-user",
        authorization="Bearer old-token",
    )

    updated = _with_header_identity(request, "Bearer current-token", "current-user")

    assert updated.uid == "current-user"
    assert updated.authorization == "Bearer current-token"


def test_chat_api_uses_tenant_prompt_without_removing_rag_evidence(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.milvus_service.search",
        lambda *args, **kwargs: [{"chunk_id": "chunk-1", "text": "制度内容", "score": 0.9}],
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.model_service.rerank",
        lambda query, evidence, **kwargs: evidence[: kwargs["top_k"]],
    )
    calls = {}

    def fake_answer(question, **kwargs):
        calls.update({"question": question, **kwargs})
        return "回答"

    monkeypatch.setattr("ai_erp_rag_assistant.app.api.model_service.answer", fake_answer)
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_identity",
        lambda request, authorization, uid: (
            request,
            request.company_id,
            request.department,
            ["knowledge:handbook"],
        ),
    )
    response = rag_chat(
        RagChatRequest(
            query="制度是什么？",
            company_id="C001",
            knowledge_base_key="handbook",
            system_context="使用正式语气",
        ),
        None,
        None,
    )

    assert response.message == "回答"
    assert response.count == 1
    assert calls["system_context"] == "使用正式语气"
    assert calls["evidence"][0]["chunk_id"] == "chunk-1"


def test_search_applies_verified_permission_filter(monkeypatch):
    service = MilvusService()
    calls = {}

    class FakeClient:
        @staticmethod
        def has_collection(name):
            return True

        @staticmethod
        def search(**kwargs):
            calls.update(kwargs)
            return [[]]

    monkeypatch.setattr(service, "_client", lambda: FakeClient())
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.milvus_service.embedding_service.embed_query",
        lambda query: [0.1, 0.2],
    )

    service.search(
        "制度",
        company_id="C001",
        permission_tags=["knowledge:handbook"],
    )

    assert "ARRAY_LENGTH(permission_tags) == 0" in calls["filter"]
    assert 'ARRAY_CONTAINS_ANY(permission_tags, ["knowledge:handbook"])' in calls["filter"]


def test_search_without_verified_department_is_limited_to_public_documents(monkeypatch):
    service = MilvusService()
    calls = {}

    class FakeClient:
        @staticmethod
        def has_collection(name):
            return True

        @staticmethod
        def search(**kwargs):
            calls.update(kwargs)
            return [[]]

    monkeypatch.setattr(service, "_client", lambda: FakeClient())
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.milvus_service.embedding_service.embed_query",
        lambda query: [0.1, 0.2],
    )

    service.search("制度", company_id="C001", department="", permission_tags=[])

    assert 'department == ""' in calls["filter"]
    assert 'department == "公共制度"' in calls["filter"]


def test_document_list_groups_chunks_by_source_and_version(monkeypatch):
    service = MilvusService()

    class FakeClient:
        @staticmethod
        def has_collection(name):
            return True

        @staticmethod
        def query(**kwargs):
            return [
                {
                    "chunk_id": "1",
                    "source": "policy.pdf",
                    "title": "制度",
                    "version": "2026",
                    "page": 1,
                    "permission_tags": [],
                },
                {
                    "chunk_id": "2",
                    "source": "policy.pdf",
                    "title": "制度",
                    "version": "2026",
                    "page": 3,
                    "permission_tags": [],
                },
            ]

    monkeypatch.setattr(service, "_client", lambda: FakeClient())

    items, total = service.list_documents(
        company_id="C001",
        collection_name="c001_handbook",
        keyword="制度",
    )

    assert total == 1
    assert items[0]["chunk_count"] == 2
    assert items[0]["page_count"] == 3


def test_document_delete_is_scoped_to_exact_source_and_version(monkeypatch):
    service = MilvusService()
    calls = {}

    class FakeClient:
        @staticmethod
        def has_collection(name):
            return True

        @staticmethod
        def query(**kwargs):
            calls["query_filter"] = kwargs["filter"]
            return [{"chunk_id": "1"}, {"chunk_id": "2"}]

        @staticmethod
        def delete(**kwargs):
            calls["delete_filter"] = kwargs["filter"]
            return {"delete_count": 2}

    monkeypatch.setattr(service, "_client", lambda: FakeClient())

    deleted = service.delete_document(
        company_id="C001",
        source="policy.pdf",
        version="2026",
        collection_name="c001_handbook",
    )

    assert deleted == 2
    assert 'company_id == "C001"' in calls["delete_filter"]
    assert 'source == "policy.pdf"' in calls["delete_filter"]
    assert 'version == "2026"' in calls["delete_filter"]
    assert calls["query_filter"] == calls["delete_filter"]


def test_runtime_permission_policy_can_only_narrow_verified_access():
    from ai_erp_rag_assistant.app.rag_admin_repository import RagRuntimeConfig

    runtime = RagRuntimeConfig(
        collection="c001_handbook",
        permission_policies=(
            {
                "allowed_departments": ["研发部"],
                "required_tags": ["employee"],
                "write_required_tags": ["knowledge:write"],
            },
        ),
    )

    runtime.require_access(
        department="研发部",
        permission_tags=["employee", "knowledge:write"],
        action="write",
    )
    with pytest.raises(PermissionError, match="缺少"):
        runtime.require_access(
            department="研发部", permission_tags=["employee"], action="write"
        )
    with pytest.raises(PermissionError, match="部门"):
        runtime.require_access(
            department="财务部",
            permission_tags=["employee", "knowledge:write"],
            action="write",
        )


def test_failed_milvus_upsert_cleans_only_new_chunk_ids(monkeypatch):
    service = MilvusService()
    calls = {}

    class FakeClient:
        @staticmethod
        def query(**kwargs):
            return [{"chunk_id": "old-chunk"}]

        @staticmethod
        def upsert(**kwargs):
            raise OSError("partial write")

        @staticmethod
        def delete(**kwargs):
            calls["ids"] = kwargs["ids"]

    monkeypatch.setattr(service, "ensure_collection", lambda name: name)
    monkeypatch.setattr(service, "_client", lambda: FakeClient())
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.milvus_service.embedding_service.embed_documents",
        lambda texts: [[0.1, 0.2] for _ in texts],
    )

    with pytest.raises(RuntimeError, match="可安全重试"):
        service.upsert_chunks(
            [
                {
                    "chunk_id": "new-chunk",
                    "text": "新制度",
                    "source": "policy.txt",
                    "company_id": "C001",
                    "version": "2026",
                }
            ],
            company_id="C001",
            collection_name="c001_handbook",
            replace_existing=True,
        )

    assert calls["ids"] == ["new-chunk"]


def test_reimport_allows_unversioned_document_without_broadening_scope(monkeypatch):
    service = MilvusService()
    calls = {}

    class FakeClient:
        @staticmethod
        def query(**kwargs):
            calls["filter"] = kwargs["filter"]
            return []

        @staticmethod
        def upsert(**kwargs):
            calls["upsert"] = kwargs

    monkeypatch.setattr(service, "ensure_collection", lambda name: name)
    monkeypatch.setattr(service, "_client", lambda: FakeClient())
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.milvus_service.embedding_service.embed_documents",
        lambda texts: [[0.1, 0.2] for _ in texts],
    )

    inserted = service.upsert_chunks(
        [
            {
                "chunk_id": "unversioned",
                "text": "未版本化制度",
                "source": "policy.txt",
                "company_id": "C001",
                "version": "",
            }
        ],
        company_id="C001",
        collection_name="c001_handbook",
        replace_existing=True,
    )

    assert inserted == 1
    assert 'source == "policy.txt"' in calls["filter"]
    assert 'version == ""' in calls["filter"]


def test_retry_acl_precheck_runs_before_creating_new_job(monkeypatch, tmp_path):
    source_path = tmp_path / "source.txt"
    source_path.write_text("制度内容", encoding="utf-8")
    (tmp_path / "request.json").write_text(
        json.dumps({"permission_tags": ["old-role"]}), encoding="utf-8"
    )

    class FakeRepository:
        def __init__(self, session):
            self.created = False

        def get_ingest_job(self, company_id, job_id):
            return (
                SimpleNamespace(status="failed"),
                SimpleNamespace(status="failed", storage_uri=str(source_path)),
                SimpleNamespace(id=7, knowledge_key="handbook"),
            )

        def create_ingest_retry(self, *args, **kwargs):
            self.created = True
            raise AssertionError("ACL 失败时不应创建补偿任务")

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.ingest_job_service.RagAdminRepository",
        FakeRepository,
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.ingest_job_service._validated_storage_path",
        lambda storage_uri, company_id: source_path,
    )
    prepare_called = False

    def reject_acl(metadata):
        nonlocal prepare_called
        prepare_called = True
        raise ValueError("权限已收回")

    with pytest.raises(ValueError, match="权限已收回"):
        IngestJobTracker.retry(
            object(),
            company_id="C001",
            knowledge_base_key="handbook",
            failed_job_id=10,
            prepare_metadata=reject_acl,
        )

    assert prepare_called is True

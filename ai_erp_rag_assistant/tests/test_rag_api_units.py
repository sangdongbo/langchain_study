from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from ai_erp_rag_assistant.app.api import (
    _persistent_identity,
    _rag_identity,
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
        chunk_size=100,
        chunk_overlap=10,
    )

    assert rows[0]["page"] == 1
    assert rows[0]["company_id"] == "C001"
    assert empty_pages == [2]


def test_search_api_forwards_tenant_and_knowledge_base(monkeypatch):
    calls = {}

    def fake_search(query, **kwargs):
        calls.update({"query": query, **kwargs})
        return [{"chunk_id": "chunk-1", "score": 0.9}]

    monkeypatch.setattr("ai_erp_rag_assistant.app.api.milvus_service.search", fake_search)
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_identity",
        lambda request, authorization, uid: (request, request.company_id, request.department),
    )
    response = rag_search(
        RagSearchRequest(query="病假材料", company_id="C001", knowledge_base_key="handbook"),
        None,
        None,
    )

    assert response.count == 1
    assert calls["company_id"] == "C001"
    assert calls["knowledge_base_key"] == "handbook"


def test_rag_identity_rejects_company_switch(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._erp_user",
        lambda request: {"company_id": "C002", "department": "研发部"},
    )

    with pytest.raises(HTTPException) as error:
        _rag_identity(RagSearchRequest(query="制度", company_id="C001"), None, None)

    assert error.value.status_code == 403


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


def test_chat_api_uses_tenant_prompt_without_removing_rag_evidence(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.milvus_service.search",
        lambda *args, **kwargs: [{"chunk_id": "chunk-1", "text": "制度内容", "score": 0.9}],
    )
    calls = {}

    def fake_answer(question, **kwargs):
        calls.update({"question": question, **kwargs})
        return "回答"

    monkeypatch.setattr("ai_erp_rag_assistant.app.api.model_service.answer", fake_answer)
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_identity",
        lambda request, authorization, uid: (request, request.company_id, request.department),
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

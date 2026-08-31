import asyncio
from io import BytesIO
from zipfile import ZipFile

from starlette.requests import Request

from ai_erp_rag_assistant.app.api import rag_ingest_document
from ai_erp_rag_assistant.app.services.document_ingest_service import (
    build_chunk_rows,
    parse_document,
)
from ai_erp_rag_assistant.app.services.milvus_service import MilvusService


def _request(body: bytes) -> Request:
    async def receive() -> dict[str, object]:
        return {"type": "http.request", "body": body, "more_body": False}

    return Request(
        {
            "type": "http",
            "method": "POST",
            "path": "/api/rag/ingest/document",
            "headers": [],
        },
        receive,
    )


def test_text_document_parser_preserves_chunk_metadata():
    rows, empty_pages = build_chunk_rows(
        "第一条制度。第二条制度。".encode(),
        company_id="C001",
        source="policy.txt",
        knowledge_base_key="handbook",
        department="公共制度",
        version="2026",
        effective_date="2026-01-01",
        permission_tags=["hr", " manager "],
        chunk_size=100,
        chunk_overlap=10,
    )

    assert empty_pages == []
    assert rows
    assert rows[0]["company_id"] == "C001"
    assert rows[0]["permission_tags"] == ["hr", "manager"]
    assert rows[0]["page"] == 1
    assert rows[0]["version"] == "2026"


def test_docx_parser_extracts_paragraphs_without_external_converter():
    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body><w:p><w:r><w:t>DOCX 制度内容</w:t></w:r></w:p></w:body></w:document>"
    )
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    rows, _ = build_chunk_rows(
        content.getvalue(),
        company_id="C001",
        source="policy.docx",
        chunk_size=100,
        chunk_overlap=0,
    )

    assert rows[0]["text"] == "DOCX 制度内容"
    assert rows[0]["source"] == "policy.docx"


def test_docx_parser_keeps_table_rows_as_searchable_records():
    document_xml = (
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>"
        "<w:tbl><w:tr><w:tc><w:p><w:r><w:t>字段</w:t></w:r></w:p></w:tc>"
        "<w:tc><w:p><w:r><w:t>值</w:t></w:r></w:p></w:tc></w:tr></w:tbl>"
        "</w:body></w:document>"
    )
    content = BytesIO()
    with ZipFile(content, "w") as archive:
        archive.writestr("word/document.xml", document_xml)

    pages, _ = parse_document(content.getvalue(), "table.docx")

    assert pages[0].text == "字段 | 值"


def test_structured_text_parsers_remove_markup_and_keep_fields():
    html_pages, _ = parse_document(
        "<html><body><h1>制度</h1><script>ignore()</script><p>请假流程</p></body></html>".encode(),
        "policy.html",
    )
    json_pages, _ = parse_document('{"department":"研发","enabled":true}'.encode(), "policy.json")
    csv_pages, _ = parse_document("name,rule\n病假,需要材料\n".encode(), "policy.csv")

    assert "ignore" not in html_pages[0].text
    assert "制度" in html_pages[0].text and "请假流程" in html_pages[0].text
    assert '"department": "研发"' in json_pages[0].text
    assert "name: 病假；rule: 需要材料" in csv_pages[0].text


def test_text_decoder_honors_utf16_bom_and_csv_quoted_newlines():
    utf16_pages, _ = parse_document("第一行制度\n第二行".encode("utf-16"), "policy.txt")
    csv_pages, _ = parse_document(
        'name,rule\n病假,"需要\n就医材料"\n'.encode(),
        "policy.csv",
    )

    assert "第一行制度" in utf16_pages[0].text
    assert "就医材料" in csv_pages[0].text


def test_document_ingest_api_runs_parse_embedding_and_milvus_in_one_request(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.get_current_user",
        lambda *args, **kwargs: {"company_id": "C001", "department": "研发部"},
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_runtime_config",
        lambda *args, **kwargs: type("Runtime", (), {"collection": "c001_handbook"})(),
    )
    calls: dict[str, object] = {}

    def fake_upsert(rows, **kwargs):
        calls["rows"] = rows
        calls["kwargs"] = kwargs
        return len(rows)

    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.milvus_service.upsert_chunks", fake_upsert
    )
    response = asyncio.run(
        rag_ingest_document(
            _request("研发制度内容".encode()),
            company_id="C001",
            source="policy.txt",
            user_id="U001",
            knowledge_base_key="handbook",
            permission_tags="研发, manager ",
            chunk_size=100,
            chunk_overlap=10,
            db=None,
        )
    )

    assert response.status == "completed"
    assert response.company_id == "C001"
    assert response.collection == "c001_handbook"
    assert response.inserted_count == response.chunk_count
    assert calls["kwargs"] == {
        "company_id": "C001",
        "knowledge_base_key": "handbook",
        "collection_name": "c001_handbook",
    }
    assert calls["rows"][0]["department"] == "研发部"
    assert calls["rows"][0]["permission_tags"] == ["研发", "manager"]


def test_document_ingest_uses_knowledge_base_chunk_defaults(monkeypatch):
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api.get_current_user",
        lambda *args, **kwargs: {"company_id": "C001", "department": "研发部"},
    )
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.api._rag_runtime_config",
        lambda *args, **kwargs: type(
            "Runtime",
            (),
            {"collection": "c001_handbook", "chunk_size": 200, "chunk_overlap": 20},
        )(),
    )
    captured: dict[str, int] = {}

    def fake_build(content, **kwargs):
        captured["chunk_size"] = kwargs["chunk_size"]
        captured["chunk_overlap"] = kwargs["chunk_overlap"]
        return ([{"text": "制度", "company_id": "C001"}], [])

    monkeypatch.setattr("ai_erp_rag_assistant.app.api.build_chunk_rows", fake_build)
    monkeypatch.setattr("ai_erp_rag_assistant.app.api.milvus_service.upsert_chunks", lambda rows, **kwargs: 1)

    asyncio.run(
        rag_ingest_document(
            _request("制度".encode()),
            company_id="C001",
            source="policy.txt",
            db=None,
        )
    )

    assert captured == {"chunk_size": 200, "chunk_overlap": 20}


def test_milvus_upsert_embeds_rows_before_writing(monkeypatch):
    service = MilvusService()
    writes: dict[str, object] = {}

    class FakeClient:
        def upsert(self, **kwargs):
            writes.update(kwargs)

    monkeypatch.setattr(service, "ensure_collection", lambda name: name)
    monkeypatch.setattr(service, "_client", lambda: FakeClient())
    monkeypatch.setattr(
        "ai_erp_rag_assistant.app.services.milvus_service.embedding_service.embed_documents",
        lambda texts: [[0.1, 0.2] for _ in texts],
    )

    inserted = service.upsert_chunks(
        [
            {
                "chunk_id": "C001:handbook:1",
                "text": "制度内容",
                "source": "policy.txt",
                "page": 1,
                "title": "制度",
                "company_id": "C001",
                "department": "公共制度",
                "version": "2026",
                "effective_date": "",
                "is_active": True,
                "permission_tags": [],
            }
        ],
        company_id="C001",
        knowledge_base_key="handbook",
        collection_name="c001_handbook",
    )

    assert inserted == 1
    assert writes["collection_name"] == "c001_handbook"
    assert writes["data"][0]["dense"] == [0.1, 0.2]


def test_milvus_rejects_existing_collection_with_wrong_dimension(monkeypatch):
    service = MilvusService()

    class FakeClient:
        def has_collection(self, name):
            return True

        def describe_collection(self, name):
            return {"fields": [{"field_name": "dense", "params": {"dim": 1536}}]}

    monkeypatch.setattr(service, "_client", lambda: FakeClient())

    try:
        service.ensure_collection("c001_handbook")
    except RuntimeError as exc:
        assert "1536" in str(exc)
        assert "2048" in str(exc)
    else:
        raise AssertionError("应拒绝向量维度不匹配的 Collection")


def test_milvus_search_rejects_existing_collection_with_wrong_dimension(monkeypatch):
    service = MilvusService()

    class FakeClient:
        def has_collection(self, name):
            return True

        def describe_collection(self, name):
            return {"fields": [{"name": "dense", "type_params": {"dim": 1536}}]}

    monkeypatch.setattr(service, "_client", lambda: FakeClient())

    try:
        service.search("制度", company_id="C001")
    except RuntimeError as exc:
        assert "1536" in str(exc)
        assert "2048" in str(exc)
    else:
        raise AssertionError("检索前应拒绝向量维度不匹配的 Collection")

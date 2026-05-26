from __future__ import annotations

import pytest
from langchain_core.documents import Document
from langchain_core.runnables import RunnableLambda

from agent_demo.config.settings import load_settings
from agent_demo.model.factory import create_chat_model
from agent_demo.rag.rag_service import RagSummarizeService
from agent_demo.rag.vector_store import (
    IndexingResult,
    LocalHashEmbeddings,
    documents_from_uploads,
    file_md5,
    format_documents,
    split_documents,
)
from agent_demo.utils.file_handler import UploadedText, clean_text, decode_uploaded_bytes
from agent_demo.utils.logger_handler import LogStore, make_log
from agent_demo.utils.path_tools import AGENT_DEMO_ROOT, chroma_dir, logs_dir, prompt_path
from agent_demo.utils.prompt_loader import load_prompt


def test_paths_resolve_inside_agent_demo() -> None:
    assert AGENT_DEMO_ROOT.name == "agent_demo"
    assert chroma_dir() == AGENT_DEMO_ROOT / "chroma_db"
    assert logs_dir() == AGENT_DEMO_ROOT / "logs"
    assert prompt_path("agent_system.md") == AGENT_DEMO_ROOT / "prompts" / "agent_system.md"


def test_logger_store_keeps_recent_entries(tmp_path) -> None:
    store = LogStore(max_entries=2, log_dir=tmp_path)
    store.add(make_log("one", "first"))
    store.add(make_log("two", "second"))
    store.add(make_log("three", "third"))

    rendered = store.render_lines()

    assert len(rendered) == 2
    assert "two：second" in rendered[0]
    assert "three：third" in rendered[1]


def test_logger_store_writes_entries_to_daily_file(tmp_path) -> None:
    store = LogStore(log_dir=tmp_path)
    entry = make_log("工具", "调用天气工具")

    store.add(entry)

    log_file = tmp_path / f"{entry.date}.log"
    assert log_file.exists()
    assert log_file.read_text(encoding="utf-8").strip() == entry.render()


def test_clean_text_collapses_excess_blank_lines() -> None:
    assert clean_text("  第一段\n\n\n\n第二段  ") == "第一段\n\n第二段"


def test_decode_uploaded_bytes_prefers_utf8() -> None:
    uploaded = decode_uploaded_bytes("demo.md", "你好".encode("utf-8"))

    assert uploaded == UploadedText(name="demo.md", text="你好", encoding="utf-8")


def test_decode_uploaded_bytes_falls_back_to_gb18030() -> None:
    uploaded = decode_uploaded_bytes("demo.txt", "中文".encode("gb18030"))

    assert uploaded.name == "demo.txt"
    assert uploaded.text == "中文"
    assert uploaded.encoding == "gb18030"


def test_load_prompt_reads_existing_prompt() -> None:
    text = load_prompt("agent_system.md")

    assert "学习型智能体" in text


def test_load_prompt_reports_missing_prompt() -> None:
    with pytest.raises(FileNotFoundError, match="缺少 prompt 文件"):
        load_prompt("missing.md")


def test_load_settings_uses_deepseek_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_TEMPERATURE", "0.3")

    settings = load_settings()

    assert settings.chat_provider == "deepseek"
    assert settings.chat_model == "deepseek-chat"
    assert settings.temperature == 0.3


def test_load_settings_falls_back_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    settings = load_settings()

    assert settings.chat_provider == "openai"
    assert settings.chat_model == "gpt-test"
    assert settings.openai_base_url == "https://example.test/v1"


def test_local_hash_embeddings_are_deterministic() -> None:
    embeddings = LocalHashEmbeddings(dimensions=32)

    first = embeddings.embed_query("智能体")
    second = embeddings.embed_query("智能体")

    assert first == second
    assert len(first) == 32


def test_documents_from_uploads_adds_metadata() -> None:
    docs = documents_from_uploads([UploadedText(name="a.md", text="内容", encoding="utf-8")])

    assert len(docs) == 1
    assert docs[0].page_content == "内容"
    assert docs[0].metadata["source"] == "a.md"
    assert docs[0].metadata["suffix"] == ".md"
    assert docs[0].metadata["file_md5"] == file_md5("内容")


def test_split_documents_keeps_metadata() -> None:
    docs = [Document(page_content="第一段。" * 80, metadata={"source": "a.md"})]

    chunks = split_documents(docs, chunk_size=60, chunk_overlap=10)

    assert len(chunks) > 1
    assert all(chunk.metadata["source"] == "a.md" for chunk in chunks)


def test_format_documents_includes_sources() -> None:
    docs = [Document(page_content="知识点", metadata={"source": "a.md"})]

    formatted = format_documents(docs)

    assert "来源：a.md" in formatted
    assert "知识点" in formatted


def test_indexing_result_summary_mentions_skipped_files() -> None:
    result = IndexingResult(added_chunks=2, skipped_files=["a.md"], indexed_files=[])

    assert result.summary() == "写入 2 个文本块，跳过重复文件：a.md"


def test_create_chat_model_reports_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="缺少 OPENAI_API_KEY 或 DEEPSEEK_API_KEY"):
        create_chat_model()


class FakeVectorStoreService:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    def retrieve(self, query: str, k: int = 4) -> list[Document]:
        self.calls.append((query, k))
        return [Document(page_content=f"{query} 的资料", metadata={"source": "fake.md"})]


def test_rag_service_retrieve_docs_uses_vector_store() -> None:
    service = RagSummarizeService(vector_store=FakeVectorStoreService())

    docs = service.retrieve_docs("智能体", k=2)

    assert docs[0].page_content == "智能体 的资料"


def test_rag_service_answer_uses_context_and_question() -> None:
    model = RunnableLambda(lambda prompt_value: "基于资料回答")
    service = RagSummarizeService(vector_store=FakeVectorStoreService(), model=model)

    answer = service.answer("智能体是什么？")

    assert answer == "基于资料回答"


def test_rag_service_summarize_uses_summary_prompt() -> None:
    model = RunnableLambda(lambda prompt_value: "总结结果")
    service = RagSummarizeService(vector_store=FakeVectorStoreService(), model=model)

    answer = service.rag_summarize("智能体")

    assert answer == "总结结果"


def test_rag_answer_chain_retrieves_context_inside_lcel() -> None:
    vector_store = FakeVectorStoreService()

    def fake_model(prompt_value) -> str:
        text = prompt_value.to_string()
        assert "智能体是什么？ 的资料" in text
        assert "问题：智能体是什么？" in text
        return "模型优化后的回答"

    service = RagSummarizeService(vector_store=vector_store, model=RunnableLambda(fake_model))

    answer = service.build_answer_chain(k=3).invoke("智能体是什么？")

    assert answer == "模型优化后的回答"
    assert vector_store.calls == [("智能体是什么？", 3)]


def test_rag_summary_chain_retrieves_context_inside_lcel() -> None:
    vector_store = FakeVectorStoreService()

    def fake_model(prompt_value) -> str:
        text = prompt_value.to_string()
        assert "智能体 的资料" in text
        assert "总结主题：智能体" in text
        return "模型优化后的总结"

    service = RagSummarizeService(vector_store=vector_store, model=RunnableLambda(fake_model))

    answer = service.build_summary_chain(k=2).invoke("智能体")

    assert answer == "模型优化后的总结"
    assert vector_store.calls == [("智能体", 2)]

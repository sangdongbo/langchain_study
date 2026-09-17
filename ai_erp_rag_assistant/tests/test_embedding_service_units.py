import math
from types import SimpleNamespace

import pytest

from ai_erp_rag_assistant.app.services.embedding_service import EmbeddingService


def _settings(**overrides):
    values = {
        "embedding_api_key": "test-key",
        "embedding_base_url": "https://embedding.example/v1",
        "embedding_model": "text-embedding-test",
        "embedding_dimensions": 3,
        "embedding_timeout": 17.0,
        "embedding_max_retries": 4,
    }
    values.update(overrides)
    return SimpleNamespace(**values)


def test_embedding_client_is_reused_and_receives_runtime_controls(monkeypatch):
    created = []

    class FakeEmbeddings:
        def __init__(self, **kwargs):
            created.append(kwargs)

        def embed_documents(self, texts):
            return [[1.0, 2.0, 3.0] for _ in texts]

        def embed_query(self, text):
            return [1.0, 2.0, 3.0]

    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)
    service = EmbeddingService()
    service.settings = _settings()

    assert service.embed_query("病假") == [1.0, 2.0, 3.0]
    assert service.embed_documents(["制度一", "制度二"]) == [
        [1.0, 2.0, 3.0],
        [1.0, 2.0, 3.0],
    ]
    assert len(created) == 1
    assert created[0]["timeout"] == 17.0
    assert created[0]["max_retries"] == 4


def test_embedding_rejects_provider_returning_wrong_document_count(monkeypatch):
    class FakeEmbeddings:
        def __init__(self, **kwargs):
            pass

        def embed_documents(self, texts):
            return [[1.0, 2.0, 3.0]]

    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)
    service = EmbeddingService()
    service.settings = _settings()

    with pytest.raises(RuntimeError, match="数量异常"):
        service.embed_documents(["制度一", "制度二"])


def test_embedding_rejects_provider_returning_wrong_dimension(monkeypatch):
    class FakeEmbeddings:
        def __init__(self, **kwargs):
            pass

        def embed_query(self, text):
            return [1.0, 2.0]

    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)
    service = EmbeddingService()
    service.settings = _settings()

    with pytest.raises(RuntimeError, match="维度异常"):
        service.embed_query("制度")


def test_embedding_rejects_non_finite_values(monkeypatch):
    class FakeEmbeddings:
        def __init__(self, **kwargs):
            pass

        def embed_query(self, text):
            return [1.0, math.nan, 3.0]

    monkeypatch.setattr("langchain_openai.OpenAIEmbeddings", FakeEmbeddings)
    service = EmbeddingService()
    service.settings = _settings()

    with pytest.raises(RuntimeError, match="非有限"):
        service.embed_query("制度")

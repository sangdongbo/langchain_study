from __future__ import annotations

from ai_erp_rag_assistant.app.config import get_settings


class EmbeddingService:
    """OpenAI-compatible embeddings, normally DashScope text-embedding-v4."""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _embeddings(self):
        if not self.settings.embedding_api_key:
            raise RuntimeError("未配置 EMBEDDING_API_KEY 或 DASHSCOPE_API_KEY，无法写入/检索 Milvus。")
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as exc:
            raise RuntimeError("缺少 langchain-openai，请执行 uv sync。") from exc
        kwargs = {
            "model": self.settings.embedding_model,
            "api_key": self.settings.embedding_api_key,
            "dimensions": self.settings.embedding_dimensions,
            "chunk_size": 10,
            "check_embedding_ctx_length": False,
        }
        if self.settings.embedding_base_url:
            kwargs["base_url"] = self.settings.embedding_base_url
        return OpenAIEmbeddings(**kwargs)

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return self._embeddings().embed_documents(texts)

    def embed_query(self, text: str) -> list[float]:
        return self._embeddings().embed_query(text)


embedding_service = EmbeddingService()

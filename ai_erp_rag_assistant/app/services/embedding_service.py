"""封装 OpenAI 兼容 Embedding 客户端及部署配置检查。"""

from __future__ import annotations

import math

from ai_erp_rag_assistant.app.config import get_settings


class EmbeddingService:
    """OpenAI 兼容的 Embedding 客户端，默认使用 DashScope text-embedding-v4。"""

    def __init__(self) -> None:
        self.settings = get_settings()
        # Embedding 客户端内部持有 HTTP 连接池；进程内复用可减少每次导入/检索的连接开销。
        self._client = None
        self._client_key: tuple[str, str, str, int, float, int] | None = None

    def _embeddings(self):
        if not self.settings.embedding_api_key:
            raise RuntimeError("未配置 EMBEDDING_API_KEY 或 DASHSCOPE_API_KEY，无法写入/检索 Milvus。")
        try:
            from langchain_openai import OpenAIEmbeddings
        except ImportError as exc:
            raise RuntimeError("缺少 langchain-openai，请执行 uv sync。") from exc
        cache_key = (
            self.settings.embedding_base_url,
            self.settings.embedding_api_key,
            self.settings.embedding_model,
            self.settings.embedding_dimensions,
            self.settings.embedding_timeout,
            self.settings.embedding_max_retries,
        )
        if self._client is not None and self._client_key == cache_key:
            return self._client
        kwargs = {
            "model": self.settings.embedding_model,
            "api_key": self.settings.embedding_api_key,
            "dimensions": self.settings.embedding_dimensions,
            "chunk_size": 10,
            "check_embedding_ctx_length": False,
            # 连接超时和重试由 Embedding 客户端统一控制，避免请求永久挂起。
            "timeout": self.settings.embedding_timeout,
            "max_retries": self.settings.embedding_max_retries,
        }
        if self.settings.embedding_base_url:
            kwargs["base_url"] = self.settings.embedding_base_url
        self._client = OpenAIEmbeddings(**kwargs)
        self._client_key = cache_key
        return self._client

    def _validate_vectors(self, vectors: list[list[float]], expected_count: int, *, kind: str) -> list[list[float]]:
        """在写入 Milvus 前校验供应商返回，防止数量或维度错位造成脏数据。"""
        if len(vectors) != expected_count:
            raise RuntimeError(f"Embedding {kind}数量异常：期望 {expected_count}，实际 {len(vectors)}")
        dimension = self.settings.embedding_dimensions
        for index, vector in enumerate(vectors, start=1):
            if len(vector) != dimension:
                raise RuntimeError(
                    f"Embedding {kind}维度异常：第 {index} 个向量为 {len(vector)}，期望 {dimension}"
                )
            if not all(
                isinstance(value, (int, float))
                and not isinstance(value, bool)
                and math.isfinite(float(value))
                for value in vector
            ):
                raise RuntimeError(f"Embedding {kind}包含非有限或非数字向量值：第 {index} 个向量")
        return vectors

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """批量生成文档 Chunk 向量。"""
        if not texts:
            return []
        try:
            vectors = self._embeddings().embed_documents(texts)
            return self._validate_vectors(vectors, len(texts), kind="文档向量")
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Embedding 文档向量生成失败：{exc}") from exc

    def embed_query(self, text: str) -> list[float]:
        """生成单个检索问题向量。"""
        try:
            vector = self._embeddings().embed_query(text)
            return self._validate_vectors([vector], 1, kind="查询向量")[0]
        except RuntimeError:
            raise
        except Exception as exc:
            raise RuntimeError(f"Embedding 查询向量生成失败：{exc}") from exc


embedding_service = EmbeddingService()

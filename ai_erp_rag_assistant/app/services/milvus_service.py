from __future__ import annotations

from typing import Any

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.services.embedding_service import embedding_service


OUTPUT_FIELDS = [
    "chunk_id", "text", "source", "page", "title", "company_id", "department",
    "version", "effective_date", "is_active", "permission_tags",
]


class MilvusService:
    def __init__(self) -> None:
        self.settings = get_settings()

    def _client(self):
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RuntimeError("缺少 pymilvus，请执行 uv sync。") from exc
        return MilvusClient(uri=self.settings.milvus_uri, token=self.settings.milvus_token or None)

    def ensure_collection(self) -> None:
        from pymilvus import DataType

        client = self._client()
        if client.has_collection(self.settings.milvus_collection):
            return
        schema = client.create_schema(auto_id=False, enable_dynamic_field=False)
        schema.add_field("chunk_id", DataType.VARCHAR, is_primary=True, max_length=512)
        schema.add_field("text", DataType.VARCHAR, max_length=8000)
        schema.add_field("dense", DataType.FLOAT_VECTOR, dim=self.settings.embedding_dimensions)
        schema.add_field("source", DataType.VARCHAR, max_length=1000)
        schema.add_field("page", DataType.INT64)
        schema.add_field("title", DataType.VARCHAR, max_length=1000)
        schema.add_field("company_id", DataType.VARCHAR, max_length=256)
        schema.add_field("department", DataType.VARCHAR, max_length=256)
        schema.add_field("version", DataType.VARCHAR, max_length=128)
        schema.add_field("effective_date", DataType.VARCHAR, max_length=128)
        schema.add_field("is_active", DataType.BOOL)
        schema.add_field("permission_tags", DataType.ARRAY, element_type=DataType.VARCHAR, max_capacity=32, max_length=256)
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="dense", index_name="dense_idx", index_type="AUTOINDEX", metric_type="COSINE")
        client.create_collection(collection_name=self.settings.milvus_collection, schema=schema, index_params=index_params)

    def upsert_chunks(self, rows: list[dict[str, Any]]) -> int:
        if not rows:
            return 0
        self.ensure_collection()
        texts = [str(row["text"]) for row in rows]
        vectors = embedding_service.embed_documents(texts)
        payload = []
        for row, vector in zip(rows, vectors, strict=True):
            item = {key: row.get(key) for key in OUTPUT_FIELDS}
            item["title"] = str(item.get("title") or "")
            item["dense"] = vector
            payload.append(item)
        self._client().upsert(collection_name=self.settings.milvus_collection, data=payload)
        return len(payload)

    def search(
        self,
        query: str,
        *,
        company_id: str,
        department: str = "",
        permission_tags: list[str] | None = None,
        top_k: int = 5,
    ) -> list[dict[str, Any]]:
        client = self._client()
        if not client.has_collection(self.settings.milvus_collection):
            raise RuntimeError(f"Milvus collection 不存在：{self.settings.milvus_collection}。请先执行 PDF 入库。")
        company_id = company_id.strip()
        if not company_id:
            raise RuntimeError("缺少 company_id，已拒绝执行无租户边界的知识检索。")
        vector = embedding_service.embed_query(query)
        filters = ["is_active == true", f'company_id == "{_escape(company_id)}"']
        if department:
            filters.append(f'(department == "公共制度" or department == "{_escape(department)}")')
        results = client.search(
            collection_name=self.settings.milvus_collection,
            data=[vector],
            anns_field="dense",
            filter=" and ".join(filters),
            limit=max(top_k * 3, top_k),
            output_fields=OUTPUT_FIELDS,
            search_params={"metric_type": "COSINE", "params": {}},
        )
        hits = results[0] if results else []
        evidence: list[dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()
        for hit in hits:
            entity = hit.get("entity", hit)
            score = float(hit.get("distance", hit.get("score", 0.0)) or 0.0)
            if score < self.settings.rag_min_score:
                continue
            chunk_id = str(entity.get("chunk_id") or "")
            if chunk_id in seen_chunk_ids:
                continue
            seen_chunk_ids.add(chunk_id)
            evidence.append({key: _plain(value) for key, value in {**entity, "score": score}.items()})
            if len(evidence) >= top_k:
                break
        return evidence


def _escape(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _plain(value: Any) -> Any:
    """Convert PyMilvus scalar/list wrappers to JSON-safe Python values."""
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_plain(item) for item in value]
    try:
        return [_plain(item) for item in value]
    except TypeError:
        return str(value)


milvus_service = MilvusService()

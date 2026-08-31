from __future__ import annotations

import re
from hashlib import sha256
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

    def collection_name(self, *, company_id: str = "", knowledge_base_key: str = "") -> str:
        """Return the configured collection or a deterministic tenant KB collection."""
        key = knowledge_base_key.strip()
        if not key:
            return self.settings.milvus_collection
        company = _collection_part(company_id, "company")
        knowledge = _collection_part(key, "knowledge")
        prefix = re.sub(r"[^a-zA-Z0-9_]+", "_", self.settings.milvus_collection).strip("_")[:30]
        return f"{prefix}_{company}_{knowledge}"

    def ensure_collection(self, collection_name: str | None = None) -> str:
        from pymilvus import DataType

        client = self._client()
        collection_name = _validate_collection_name(collection_name or self.settings.milvus_collection)
        if client.has_collection(collection_name):
            self._validate_collection_dimension(client, collection_name)
            return collection_name
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
        client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)
        return collection_name

    def _validate_collection_dimension(self, client: Any, collection_name: str) -> None:
        """Fail early when an existing Collection cannot accept current vectors."""
        describe = getattr(client, "describe_collection", None)
        if not callable(describe):
            return
        try:
            description = describe(collection_name)
        except Exception as exc:
            raise RuntimeError(f"无法读取 Milvus collection 结构：{collection_name}") from exc
        dimension = _dense_dimension(description)
        if dimension is not None and dimension != self.settings.embedding_dimensions:
            raise RuntimeError(
                f"Milvus collection 向量维度为 {dimension}，"
                f"当前 Embedding 维度为 {self.settings.embedding_dimensions}：{collection_name}"
            )

    def upsert_chunks(
        self,
        rows: list[dict[str, Any]],
        *,
        company_id: str = "",
        knowledge_base_key: str = "",
        collection_name: str = "",
    ) -> int:
        if not rows:
            return 0
        company_id = company_id.strip()
        if not company_id:
            raise ValueError("缺少 company_id，已拒绝执行无租户边界的知识入库。")
        collection_name = _validate_collection_name(
            collection_name.strip()
            or self.collection_name(company_id=company_id, knowledge_base_key=knowledge_base_key)
        )
        if any(str(row.get("company_id") or "").strip() != company_id for row in rows):
            raise ValueError("Chunk company_id 与目标租户不一致，已拒绝写入。")
        self.ensure_collection(collection_name)
        texts = [str(row["text"]) for row in rows]
        vectors = embedding_service.embed_documents(texts)
        payload = []
        for row, vector in zip(rows, vectors, strict=True):
            item = {key: row.get(key) for key in OUTPUT_FIELDS}
            item["title"] = str(item.get("title") or "")
            item["dense"] = vector
            payload.append(item)
        self._client().upsert(collection_name=collection_name, data=payload)
        return len(payload)

    def search(
        self,
        query: str,
        *,
        company_id: str,
        department: str = "",
        permission_tags: list[str] | None = None,
        top_k: int = 5,
        knowledge_base_key: str = "",
        collection_name: str = "",
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        client = self._client()
        company_id = company_id.strip()
        if not company_id:
            raise RuntimeError("缺少 company_id，已拒绝执行无租户边界的知识检索。")
        collection_name = _validate_collection_name(
            collection_name.strip()
            or self.collection_name(company_id=company_id, knowledge_base_key=knowledge_base_key)
        )
        if not client.has_collection(collection_name):
            raise RuntimeError(f"Milvus collection 不存在：{collection_name}。请先执行知识库入库。")
        self._validate_collection_dimension(client, collection_name)
        vector = embedding_service.embed_query(query)
        filters = ["is_active == true", f'company_id == "{_escape(company_id)}"']
        if department:
            filters.append(f'(department == "公共制度" or department == "{_escape(department)}")')
        results = client.search(
            collection_name=collection_name,
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
            if score < (self.settings.rag_min_score if min_score is None else min_score):
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


def _validate_collection_name(value: str) -> str:
    if len(value) > 128 or not re.fullmatch(r"[a-zA-Z0-9_]+", value):
        raise ValueError("Milvus collection 名称必须为不超过 128 位的字母、数字或下划线")
    return value


def _collection_part(value: str, label: str) -> str:
    raw = value.strip()
    if not raw:
        raise ValueError(f"缺少有效的 {label}，无法生成知识库 Collection。")
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", raw).strip("_").lower()
    prefix = normalized[:32] or label
    return f"{prefix}_{sha256(raw.encode()).hexdigest()[:12]}"


def _dense_dimension(description: Any) -> int | None:
    """Read Milvus' dimension field across client response shape variants."""
    if not isinstance(description, dict):
        return None
    for field in description.get("fields") or []:
        if not isinstance(field, dict):
            continue
        if field.get("name") != "dense" and field.get("field_name") != "dense":
            continue
        params = field.get("params") or field.get("type_params") or {}
        if isinstance(params, dict):
            value = params.get("dim") or params.get("dimension")
            if value is not None:
                return int(value)
        if isinstance(params, list):
            for item in params:
                if isinstance(item, dict) and item.get("key") in {"dim", "dimension"}:
                    return int(item["value"])
        value = field.get("dim") or field.get("dimension")
        if value is not None:
            return int(value)
    return None


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

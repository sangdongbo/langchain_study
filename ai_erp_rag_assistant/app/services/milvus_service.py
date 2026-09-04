"""封装 Milvus Collection 管理、向量写入、权限检索和文档操作。"""

from __future__ import annotations

import re
from hashlib import sha256
from typing import Any, Sequence

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.services.embedding_service import embedding_service


OUTPUT_FIELDS = [
    "chunk_id", "text", "source", "page", "title", "company_id", "department",
    "version", "effective_date", "is_active", "permission_tags",
]


class MilvusService:
    """实施 company_id 边界和知识库级 Collection 隔离的 Milvus 服务。"""

    def __init__(self) -> None:
        self.settings = get_settings()

    def _client(self):
        try:
            from pymilvus import MilvusClient
        except ImportError as exc:
            raise RuntimeError("缺少 pymilvus，请执行 uv sync。") from exc
        return MilvusClient(uri=self.settings.milvus_uri, token=self.settings.milvus_token or None)

    def collection_name(self, *, company_id: str = "", knowledge_base_key: str = "") -> str:
        """返回配置的 Collection，或生成稳定的租户知识库 Collection。"""
        key = knowledge_base_key.strip()
        if not key:
            return self.settings.milvus_collection
        company = _collection_part(company_id, "company")
        knowledge = _collection_part(key, "knowledge")
        prefix = re.sub(r"[^a-zA-Z0-9_]+", "_", self.settings.milvus_collection).strip("_")[:30]
        return f"{prefix}_{company}_{knowledge}"

    def ensure_collection(self, collection_name: str | None = None) -> str:
        """确认 Collection 存在且维度兼容，不存在时创建固定 Schema。"""
        from pymilvus import DataType

        client = self._client()
        collection_name = _validate_collection_name(collection_name or self.settings.milvus_collection)
        if client.has_collection(collection_name):
            self._validate_collection_dimension(client, collection_name)
            return collection_name
        # 固定 Schema 禁用动态字段，防止不同导入批次写出不可控的元数据结构。
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
        # COSINE 与 Embedding 检索得分语义一致，AUTOINDEX 交给 Milvus 选择实现。
        index_params = client.prepare_index_params()
        index_params.add_index(field_name="dense", index_name="dense_idx", index_type="AUTOINDEX", metric_type="COSINE")
        client.create_collection(collection_name=collection_name, schema=schema, index_params=index_params)
        return collection_name

    def _validate_collection_dimension(self, client: Any, collection_name: str) -> None:
        """当已有 Collection 无法接收当前向量时提前失败。"""
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
        replace_existing: bool = False,
    ) -> int:
        """校验租户后生成向量并写入 Chunk，可安全替换同来源版本。"""
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
        # Collection 和每行 company_id 双重校验，防止调用方把其他租户数据写入目标集合。
        try:
            self.ensure_collection(collection_name)
        except (ValueError, RuntimeError):
            raise
        except Exception as exc:
            raise RuntimeError(f"Milvus Collection 初始化失败：{exc}") from exc
        client = self._client()
        stale_chunk_ids: set[str] = set()
        if replace_existing:
            # 替换模式只允许一个明确来源和一个版本分组；空 version 表示“未版本化”，
            # 仍会被精确过滤为 version == ""，不会影响同来源的其他版本。
            sources = {str(row.get("source") or "").strip() for row in rows}
            versions = {str(row.get("version") or "").strip() for row in rows}
            if len(sources) != 1 or "" in sources or len(versions) != 1:
                raise ValueError("替换导入要求所有 Chunk 使用相同且非空的 source，并属于同一 version。")
            try:
                existing = client.query(
                    collection_name=collection_name,
                    filter=_document_filter(
                        company_id,
                        source=next(iter(sources)),
                        version=next(iter(versions)),
                    ),
                    output_fields=["chunk_id"],
                    limit=16384,
                )
            except Exception as exc:
                raise RuntimeError(f"Milvus 读取待替换 Chunk 失败：{exc}") from exc
            stale_chunk_ids = {
                str(item.get("chunk_id") or "") for item in existing if item.get("chunk_id")
            }
        # 先完成整批 Embedding，再组装与固定 Schema 对齐的写入数据。
        texts = [str(row["text"]) for row in rows]
        try:
            vectors = embedding_service.embed_documents(texts)
        except Exception as exc:
            raise RuntimeError(f"Embedding 生成失败：{exc}") from exc
        payload = []
        for row, vector in zip(rows, vectors, strict=True):
            item = {key: row.get(key) for key in OUTPUT_FIELDS}
            item["title"] = str(item.get("title") or "")
            item["dense"] = vector
            payload.append(item)
        # 新 Chunk 写入成功后才允许清理旧 ID，外部服务失败时旧知识仍然可用。
        try:
            client.upsert(collection_name=collection_name, data=payload)
        except Exception as exc:
            cleanup_error: Exception | None = None
            if replace_existing:
                # 只清理本次新增且此前不存在的 ID；重合 ID 可能是旧知识，不能盲删。
                new_chunk_ids = {
                    str(row.get("chunk_id") or "") for row in rows if row.get("chunk_id")
                } - stale_chunk_ids
                if new_chunk_ids:
                    try:
                        client.delete(
                            collection_name=collection_name,
                            ids=sorted(new_chunk_ids),
                        )
                    except Exception as cleanup_exc:
                        cleanup_error = cleanup_exc
            suffix = (
                "；部分写入清理失败，可通过任务重试再次覆盖并收敛数据"
                if cleanup_error
                else "；已尝试清理本批新增 Chunk，可安全重试"
            )
            raise RuntimeError(f"Milvus 写入失败：{exc}{suffix}") from exc
        if stale_chunk_ids:
            current_chunk_ids = {str(row.get("chunk_id") or "") for row in rows}
            stale_chunk_ids.difference_update(current_chunk_ids)
            if stale_chunk_ids:
                # 只有替换向量成功写入后，才删除旧版本向量。
                try:
                    client.delete(collection_name=collection_name, ids=sorted(stale_chunk_ids))
                except Exception as exc:
                    # 新版本已经可用，重试同一请求会再次计算 stale IDs 并完成收敛。
                    raise RuntimeError(
                        f"新 Chunk 已写入，但旧 Chunk 清理失败：{exc}；请重试导入"
                    ) from exc
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
        document_filters: Sequence[tuple[str, str]] | None = None,
        restrict_to_documents: bool = False,
    ) -> list[dict[str, Any]]:
        """按公司、知识库、启用文档、部门和 ACL 执行向量检索。"""
        client = self._client()
        company_id = company_id.strip()
        if not company_id:
            raise RuntimeError("缺少 company_id，已拒绝执行无租户边界的知识检索。")
        collection_name = _validate_collection_name(
            collection_name.strip()
            or self.collection_name(company_id=company_id, knowledge_base_key=knowledge_base_key)
        )
        try:
            exists = client.has_collection(collection_name)
        except Exception as exc:
            raise RuntimeError(f"Milvus Collection 状态查询失败：{exc}") from exc
        if not exists:
            raise RuntimeError(f"Milvus collection 不存在：{collection_name}。请先执行知识库入库。")
        self._validate_collection_dimension(client, collection_name)
        # 查询向量与文档向量必须来自同一进程级模型和维度配置。
        vector = embedding_service.embed_query(query)
        filters = _visibility_filters(company_id, department, permission_tags)
        if restrict_to_documents:
            # MySQL 已配置时只允许 published + search_enabled 文档的 source/version 命中。
            filters.append(_active_document_filter(document_filters or []))
        # 先多取候选，再在应用层做最低分、去重和精确 top_k 截断。
        try:
            results = client.search(
                collection_name=collection_name,
                data=[vector],
                anns_field="dense",
                filter=" and ".join(filters),
                limit=max(top_k * 3, top_k),
                output_fields=OUTPUT_FIELDS,
                search_params={"metric_type": "COSINE", "params": {}},
            )
        except Exception as exc:
            raise RuntimeError(f"Milvus 向量检索失败：{exc}") from exc
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
            evidence_item = {
                key: _plain(value) for key, value in {**entity, "score": score}.items()
            }
            if knowledge_base_key:
                # Collection 内没有重复存储知识库标识，服务端检索时补齐可信来源。
                evidence_item["knowledge_base_key"] = knowledge_base_key
            evidence.append(evidence_item)
            if len(evidence) >= top_k:
                break
        return evidence

    def search_many(
        self,
        query: str,
        *,
        company_id: str,
        department: str = "",
        permission_tags: list[str] | None = None,
        targets: Sequence[dict[str, Any]] = (),
        top_k: int = 5,
        min_score: float | None = None,
    ) -> list[dict[str, Any]]:
        """跨公司内多个启用知识库检索，并按统一得分合并候选结果。"""
        merged: list[dict[str, Any]] = []
        seen_chunk_ids: set[str] = set()
        for target in targets:
            key = str(target.get("knowledge_base_key") or "").strip()
            collection = str(target.get("collection") or "").strip()
            if not collection:
                continue
            try:
                rows = self.search(
                    query,
                    company_id=company_id,
                    department=department,
                    permission_tags=permission_tags,
                    top_k=top_k,
                    knowledge_base_key=key,
                    collection_name=collection,
                    min_score=(
                        min_score
                        if min_score is not None
                        else target.get("score_threshold")
                    ),
                    document_filters=target.get("active_documents") or (),
                    restrict_to_documents=bool(target.get("document_scope_loaded")),
                )
            except RuntimeError as exc:
                # 公司下新建但尚未导入文件的知识库没有 Collection，不应阻断其他知识库。
                if "collection 不存在" in str(exc):
                    continue
                raise
            for row in rows:
                chunk_id = str(row.get("chunk_id") or "")
                if chunk_id and chunk_id in seen_chunk_ids:
                    continue
                if chunk_id:
                    seen_chunk_ids.add(chunk_id)
                item = dict(row)
                item["knowledge_base_key"] = key
                item["knowledge_base_name"] = str(
                    target.get("knowledge_base_name") or key
                )
                item["collection"] = collection
                merged.append(item)
        merged.sort(key=lambda item: float(item.get("score") or 0.0), reverse=True)
        return merged[:top_k]

    def list_documents(
        self,
        *,
        company_id: str,
        department: str = "",
        permission_tags: list[str] | None = None,
        collection_name: str = "",
        knowledge_base_key: str = "",
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
        document_filters: Sequence[tuple[str, str]] | None = None,
        restrict_to_documents: bool = False,
    ) -> tuple[list[dict[str, Any]], int]:
        """将可见 Milvus Chunk 按来源和版本聚合为文档摘要。"""
        company_id = company_id.strip()
        if not company_id:
            raise ValueError("company_id 不能为空")
        collection_name = _validate_collection_name(
            collection_name.strip()
            or self.collection_name(company_id=company_id, knowledge_base_key=knowledge_base_key)
        )
        client = self._client()
        try:
            if not client.has_collection(collection_name):
                return [], 0
        except Exception as exc:
            raise RuntimeError(f"Milvus Collection 状态查询失败：{exc}") from exc
        # 当前文档元数据尚未落 MySQL，先读取可见 Chunk 再按 source + version 聚合。
        query_filters = _visibility_filters(company_id, department, permission_tags)
        if restrict_to_documents:
            query_filters.append(_active_document_filter(document_filters or []))
        try:
            rows = client.query(
                collection_name=collection_name,
                filter=" and ".join(query_filters),
                output_fields=[
                    "chunk_id",
                    "source",
                    "title",
                    "version",
                    "effective_date",
                    "department",
                    "permission_tags",
                    "page",
                ],
                # ponytail：文档元数据落 MySQL 前，先使用 Milvus 查询窗口限制内存数据量。
                limit=16384,
            )
        except Exception as exc:
            raise RuntimeError(f"Milvus 文档列表查询失败：{exc}") from exc
        grouped: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            source = str(row.get("source") or "")
            version = str(row.get("version") or "")
            key = (source, version)
            item = grouped.setdefault(
                key,
                {
                    "source": source,
                    "title": str(row.get("title") or source),
                    "version": version,
                    # 单库列表也返回可信知识库来源，前端无需根据 Collection 反查。
                    "knowledge_base_key": knowledge_base_key,
                    "knowledge_base_name": knowledge_base_key,
                    "collection": collection_name,
                    "effective_date": str(row.get("effective_date") or ""),
                    "department": str(row.get("department") or ""),
                    "permission_tags": _plain(row.get("permission_tags") or []),
                    "chunk_count": 0,
                    "page_count": 0,
                },
            )
            item["chunk_count"] += 1
            item["page_count"] = max(item["page_count"], int(row.get("page") or 0))
        # 关键词只作用于用户可见文档的来源和标题，不扩大 Milvus ACL 范围。
        normalized_keyword = keyword.strip().casefold()
        items = [
            item
            for item in grouped.values()
            if not normalized_keyword
            or normalized_keyword in item["source"].casefold()
            or normalized_keyword in item["title"].casefold()
        ]
        items.sort(key=lambda item: (item["source"].casefold(), item["version"]), reverse=True)
        total = len(items)
        start = (page - 1) * page_size
        return items[start : start + page_size], total

    def list_documents_many(
        self,
        *,
        company_id: str,
        department: str = "",
        permission_tags: list[str] | None = None,
        targets: Sequence[dict[str, Any]] = (),
        keyword: str = "",
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        """聚合公司内多个启用知识库的可见文件，并补齐知识库来源。"""
        all_items: list[dict[str, Any]] = []
        for target in targets:
            try:
                items, _ = self.list_documents(
                    company_id=company_id,
                    department=department,
                    permission_tags=permission_tags,
                    collection_name=str(target.get("collection") or ""),
                    knowledge_base_key=str(target.get("knowledge_base_key") or ""),
                    keyword=keyword,
                    page=1,
                    page_size=16384,
                    document_filters=target.get("active_documents") or (),
                    restrict_to_documents=bool(target.get("document_scope_loaded")),
                )
            except RuntimeError as exc:
                if "collection 不存在" in str(exc):
                    continue
                raise
            for item in items:
                item = dict(item)
                item["knowledge_base_key"] = str(target.get("knowledge_base_key") or "")
                item["knowledge_base_name"] = str(
                    target.get("knowledge_base_name")
                    or target.get("knowledge_base_key")
                    or ""
                )
                item["collection"] = str(target.get("collection") or "")
                all_items.append(item)
        all_items.sort(
            key=lambda item: (
                str(item.get("knowledge_base_key") or "").casefold(),
                str(item.get("source") or "").casefold(),
                str(item.get("version") or ""),
            ),
            reverse=True,
        )
        total = len(all_items)
        start = (page - 1) * page_size
        return all_items[start : start + page_size], total

    def delete_document(
        self,
        *,
        company_id: str,
        source: str,
        version: str = "",
        department: str = "",
        permission_tags: list[str] | None = None,
        collection_name: str = "",
        knowledge_base_key: str = "",
    ) -> int:
        """在已验证的租户边界内精确删除一个来源/版本。"""
        company_id = company_id.strip()
        source = source.strip()
        if not company_id or not source:
            raise ValueError("company_id 和 source 不能为空")
        collection_name = _validate_collection_name(
            collection_name.strip()
            or self.collection_name(company_id=company_id, knowledge_base_key=knowledge_base_key)
        )
        client = self._client()
        try:
            if not client.has_collection(collection_name):
                return 0
        except Exception as exc:
            raise RuntimeError(f"Milvus Collection 状态查询失败：{exc}") from exc
        filters = _visibility_filters(company_id, department, permission_tags)
        filters.extend(
            [
                f'source == "{_escape(source)}"',
                f'version == "{_escape(version.strip())}"',
            ]
        )
        # 先使用最终删除表达式查询存在性，保证无权限和不存在统一返回 0。
        expression = " and ".join(filters)
        try:
            matches = client.query(
                collection_name=collection_name,
                filter=expression,
                output_fields=["chunk_id"],
                limit=16384,
            )
        except Exception as exc:
            raise RuntimeError(f"Milvus 删除前查询失败：{exc}") from exc
        if not matches:
            return 0
        # 删除复用同一表达式，避免查询后重新拼接条件造成范围漂移。
        try:
            result = client.delete(collection_name=collection_name, filter=expression)
        except Exception as exc:
            raise RuntimeError(f"Milvus 文档删除失败：{exc}") from exc
        reported = result.get("delete_count", result.get("deleted_count", 0)) if result else 0
        return int(reported or len(matches))


def _escape(value: str) -> str:
    return value.replace('\\', '\\\\').replace('"', '\\"')


def _visibility_filters(
    company_id: str,
    department: str,
    permission_tags: list[str] | None,
) -> list[str]:
    # company_id 和 is_active 始终存在；部门与 ACL 只能进一步收窄可见范围。
    filters = ["is_active == true", f'company_id == "{_escape(company_id)}"']
    public_scope = '(department == "" or department == "公共制度")'
    if department:
        filters.append(
            f'({public_scope} or department == "{_escape(department)}")'
        )
    else:
        # ERP 未返回部门时只能读取公共文档，不能通过缺失属性扩大到全公司。
        filters.append(public_scope)
    tags = sorted({str(tag).strip() for tag in permission_tags or [] if str(tag).strip()})
    if tags:
        values = ", ".join(f'"{_escape(tag)}"' for tag in tags)
        filters.append(
            f"(ARRAY_LENGTH(permission_tags) == 0 or "
            f"ARRAY_CONTAINS_ANY(permission_tags, [{values}]))"
        )
    else:
        filters.append("ARRAY_LENGTH(permission_tags) == 0")
    return filters


def _document_filter(company_id: str, *, source: str, version: str) -> str:
    return " and ".join(
        [
            f'company_id == "{_escape(company_id)}"',
            f'source == "{_escape(source)}"',
            f'version == "{_escape(version)}"',
        ]
    )


def _active_document_filter(document_filters: Sequence[tuple[str, str]]) -> str:
    """构造只允许启用文档 source/version 的 Milvus 过滤表达式。"""
    clauses = [
        f'(source == "{_escape(source)}" and version == "{_escape(version)}")'
        for source, version in document_filters
        if str(source).strip()
    ]
    # 已启用知识库但没有已发布文件时，必须返回空结果而不是放开过滤。
    return "(" + " or ".join(clauses) + ")" if clauses else '(source == "__no_active_document__")'


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
    """兼容不同客户端响应结构，读取 Milvus 向量维度字段。"""
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
    """将 PyMilvus 标量或列表包装转换为可 JSON 序列化的 Python 值。"""
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

"""HTTP 路由共用的身份认证和运行时依赖。"""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.rag_admin_repository import (
    AdminNotFoundError,
    RagAdminRepository,
    RagKnowledgeBaseTarget,
    RagRuntimeConfig,
)
from ai_erp_rag_assistant.app.services.milvus_service import milvus_service
from ai_erp_rag_assistant.app.tools.erp_tools import get_current_user


def with_header_identity(request: Any, authorization: str | None, uid: str | None) -> Any:
    """把可信的 HTTP 请求头合并到接口请求模型。"""
    return request.model_copy(
        update={
            # HTTP 请求头代表当前登录态，必须覆盖请求体中可能过期的旧凭据。
            "authorization": authorization or request.authorization or "",
            "uid": uid or request.uid or "",
        }
    )


def erp_user(request: Any) -> dict[str, Any]:
    """通过已配置的 ERP 身份提供方解析当前用户。"""
    return get_current_user(
        request.user_id,
        uid=request.uid,
        authorization=request.authorization,
        company_id=request.company_id,
        department=request.department,
    )


def persistent_identity(
    request: Any,
    authorization: str | None,
    uid: str | None,
) -> tuple[Any, dict[str, Any], str, str]:
    """使用已验证的 ERP 身份确定持久化会话归属。"""
    request = with_header_identity(request, authorization, uid)
    try:
        user = erp_user(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    company_id = str(user.get("company_id") or "").strip()
    if not company_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的 company_id")
    if request.company_id and request.company_id.strip() != company_id:
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    # 页面提交的 user_id 不能作为隔离边界，优先使用 ERP 返回的可信用户 ID。
    user_id = str(user.get("uid") or request.uid or user.get("user_id") or request.user_id).strip()
    if not user_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的用户ID")
    return request, user, company_id, user_id


def rag_identity(
    request: Any,
    authorization: str | None,
    uid: str | None,
) -> tuple[Any, str, str]:
    """在任何 RAG 读写前验证租户归属。"""
    request = with_header_identity(request, authorization, uid)
    try:
        user = erp_user(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    company_id = str(user.get("company_id") or "").strip()
    requested_company = request.company_id.strip()
    if not company_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的 company_id")
    # company_id 可省略，由 ERP 已验证身份补齐；显式填写时仍严格阻止跨租户访问。
    if requested_company and requested_company != company_id:
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    # ERP 没有部门信息时返回空值，由 Milvus 仅开放公共文档，不能回退到请求体部门。
    return request, company_id, str(user.get("department") or "").strip()


def rag_runtime_config(
    db: Session | None,
    *,
    company_id: str,
    knowledge_base_key: str,
    assistant_key: str,
    knowledge_base_keys: list[str] | tuple[str, ...] = (),
    search_scope: str | None = None,
) -> RagRuntimeConfig:
    """读取数据库中的 RAG 配置，缺失时回退到进程默认值。"""
    # 未配置 MySQL 时仍按租户和知识库 key 生成稳定、隔离的 Collection 名称。
    # 兼容旧单库参数，并让未配置 MySQL 的开发环境也能测试多库目标构造。
    requested_keys: list[str] = []
    seen_keys: set[str] = set()
    for raw_key in (*knowledge_base_keys, knowledge_base_key):
        key = str(raw_key or "").strip()
        if key and key not in seen_keys:
            requested_keys.append(key)
            seen_keys.add(key)
    if search_scope == "company_enabled" and requested_keys:
        raise ValueError("search_scope=company_enabled 时不能同时指定知识库")
    if search_scope == "selected" and not requested_keys:
        raise ValueError("search_scope=selected 时至少指定一个 knowledge_base_key")
    fallback_targets = tuple(
        RagKnowledgeBaseTarget(
            knowledge_base_key=key,
            knowledge_base_name="",
            collection=milvus_service.collection_name(
                company_id=company_id, knowledge_base_key=key
            ),
        )
        for key in requested_keys
    )
    fallback_collection = (
        fallback_targets[0].collection
        if len(fallback_targets) == 1
        else milvus_service.collection_name(
            company_id=company_id, knowledge_base_key=knowledge_base_key
        )
    )
    fallback = RagRuntimeConfig(
        collection=fallback_collection,
        chunk_size=get_settings().rag_chunk_size,
        chunk_overlap=get_settings().rag_chunk_overlap,
        rerank_enabled=get_settings().rag_rerank_enabled,
        rerank_candidates=get_settings().rag_rerank_candidates,
        retrieval_scope=("selected" if requested_keys else "company_enabled"),
        knowledge_bases=fallback_targets,
    )
    if db is None:
        return fallback
    try:
        # 数据库配置采用逐字段覆盖，避免可选字段为空时丢失默认切分参数。
        configured = RagAdminRepository(db).runtime_config(
            company_id,
            knowledge_base_key,
            assistant_key,
            knowledge_base_keys=knowledge_base_keys,
            search_scope=search_scope,
        )
        return RagRuntimeConfig(
            collection=configured.collection or fallback.collection,
            system_context=configured.system_context,
            model_overrides=configured.model_overrides,
            chunk_size=configured.chunk_size or fallback.chunk_size,
            chunk_overlap=(
                configured.chunk_overlap
                if configured.chunk_overlap is not None
                else fallback.chunk_overlap
            ),
            top_k=configured.top_k,
            score_threshold=configured.score_threshold,
            rerank_enabled=(
                configured.rerank_enabled
                if configured.rerank_enabled is not None
                else fallback.rerank_enabled
            ),
            rerank_candidates=configured.rerank_candidates or fallback.rerank_candidates,
            retrieval_scope=configured.retrieval_scope,
            permission_policies=configured.permission_policies,
            knowledge_bases=configured.knowledge_bases or fallback.knowledge_bases,
        )
    except AdminNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="MySQL 读取 RAG 配置失败") from exc

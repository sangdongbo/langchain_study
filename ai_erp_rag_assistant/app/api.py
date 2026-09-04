"""API 组合根与共享请求辅助函数。

具体端点实现位于 :mod:`app.routes`；本模块保留应用和测试依赖的稳定
``app.api`` 导入面。
"""

from __future__ import annotations

from functools import lru_cache
from hashlib import sha256
from typing import Any

import langsmith.anonymizer as langsmith_anonymizer
from fastapi import APIRouter, HTTPException
from langsmith import Client
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.rag_admin_api import router as rag_admin_router
from ai_erp_rag_assistant.app.rag_admin_repository import (
    AdminNotFoundError,
    RagAdminRepository,
    RagKnowledgeBaseTarget,
    RagRuntimeConfig,
)
from ai_erp_rag_assistant.app.services.approval_form_service import build_form_schema
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event
from ai_erp_rag_assistant.app.services.document_ingest_service import build_chunk_rows
from ai_erp_rag_assistant.app.services.milvus_service import milvus_service
from ai_erp_rag_assistant.app.services.model_service import model_service
from ai_erp_rag_assistant.app.services.session_repository import session_repository
from ai_erp_rag_assistant.app.tools.erp_tools import (
    get_approval_field_options,
    get_approval_template,
    get_current_user,
    list_approval_templates,
)
from ai_erp_rag_assistant.scripts.ingest_pdf import infer_title, split_text


# ``/api`` 是所有接口的公共前缀，各路由模块只负责自己的业务路径。
router = APIRouter(prefix="/api")
workflow = None
stateless_workflow = None

_SENSITIVE_TRACE_FIELDS = {
    "api_key",
    "authorization",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "token",
}


def _identity_anonymizer(data: Any) -> Any:
    return data


# 兼容旧版 LangSmith：如果没有 create_secret_anonymizer，仍保留字段级脱敏。
_secret_anonymizer_factory: Any = getattr(
    langsmith_anonymizer, "create_secret_anonymizer", None
)
_secret_anonymizer = (
    _secret_anonymizer_factory()
    if callable(_secret_anonymizer_factory)
    else _identity_anonymizer
)
_field_anonymizer = langsmith_anonymizer.create_anonymizer(
    lambda value, path: (
        "[REDACTED]"
        if path and str(path[-1]).lower() in _SENSITIVE_TRACE_FIELDS
        else value
    ),
    max_depth=24,
)


def _anonymize_trace(data: Any) -> Any:
    return _field_anonymizer(_secret_anonymizer(data))


@lru_cache(maxsize=1)
def _langsmith_client() -> Client | None:
    settings = get_settings()
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return None
    return Client(api_key=settings.langsmith_api_key, anonymizer=_anonymize_trace)


def _thread_id(request: Any) -> str:
    tenant = request.company_id.strip() or "default"
    principal = request.uid.strip() or request.user_id.strip()
    session = request.session_id.strip()
    digest = sha256(f"{tenant}\x1f{principal}\x1f{session}".encode()).hexdigest()
    return f"erp-rag:{digest}"


def _with_header_identity(request: Any, authorization: str | None, uid: str | None) -> Any:
    """合并请求身份；HTTP 请求头优先，JSON 字段仅用于非浏览器兼容调用。"""
    return request.model_copy(
        update={
            # 浏览器可能复用包含旧凭据的请求对象，显式请求头必须覆盖请求体中的旧值。
            "authorization": authorization or request.authorization or "",
            "uid": uid or request.uid or "",
        }
    )


def _erp_user(request: Any) -> dict[str, Any]:
    return get_current_user(
        request.user_id,
        uid=request.uid,
        authorization=request.authorization,
        company_id=request.company_id,
        department=request.department,
    )


def _verified_access_tags(user: dict[str, Any]) -> list[str]:
    """把 ERP 权限和角色规范成非空标签，并忽略显式禁用的字典项。"""
    tags: set[str] = set()

    def add(raw: Any) -> None:
        if isinstance(raw, str):
            tags.update(item.strip() for item in raw.split(",") if item.strip())
            return
        if isinstance(raw, dict):
            # ERP 常见的 {"hr": true} 权限映射不能把 false 项当成已授权标签。
            if raw and all(isinstance(enabled, bool) for enabled in raw.values()):
                tags.update(str(key).strip() for key, enabled in raw.items() if enabled and str(key).strip())
                return
            if raw.get("enabled") is False:
                return
            value = raw.get("code") or raw.get("permission") or raw.get("role") or raw.get("name") or raw.get("value")
            if value not in (None, ""):
                add(str(value))
            return
        if isinstance(raw, (list, tuple, set)):
            for item in raw:
                add(item)
            return
        if raw not in (None, ""):
            tags.add(str(raw).strip())

    # 请求体中的 permission_tags 不在这里读取；它不是可信身份来源。
    for key in ("permissions", "permission_tags", "roles", "role"):
        add(user.get(key))
    return sorted(tag for tag in tags if tag)


def _persistent_identity(
    request: Any,
    authorization: str | None,
    uid: str | None,
) -> tuple[Any, dict[str, Any], str, str]:
    """使用已验证的 ERP 身份确定持久化会话归属。"""
    # 认证头优先于请求体中的同名字段，避免客户端复用过期或伪造的身份。
    request = _with_header_identity(request, authorization, uid)
    try:
        # 持久化前必须先从 ERP 取得可信用户，后续所有归属判断都基于该结果。
        user = _erp_user(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    company_id = str(user.get("company_id") or "").strip()
    # 会话数据按公司和用户隔离；没有公司 ID 时不能安全地写入持久化存储。
    if not company_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的 company_id")
    if request.company_id and request.company_id.strip() != company_id:
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    # 页面提交的 user_id 不能作为租户隔离边界，优先使用 ERP 返回的可信 ID。
    user_id = str(user.get("uid") or request.uid or user.get("user_id") or request.user_id).strip()
    if not user_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的用户ID")
    return request, user, company_id, user_id


def _rag_identity(
    request: Any,
    authorization: str | None,
    uid: str | None,
) -> tuple[Any, str, str, list[str]]:
    """解析已验证的租户、部门以及 RAG 访问标签。"""
    # 先把 HTTP 头中的身份凭据合并到请求对象，避免信任请求体中的旧值。
    request = _with_header_identity(request, authorization, uid)
    try:
        # ERP 是身份信息的唯一可信来源；检索权限不能由前端自行声明。
        user = _erp_user(request)
    except RuntimeError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    company_id = str(user.get("company_id") or "").strip()
    requested_company = request.company_id.strip()
    # 缺少公司 ID 时无法建立租户边界，必须在进入检索前拒绝请求。
    if not company_id:
        raise HTTPException(status_code=403, detail="当前用户没有可用的 company_id")
    # 请求中的公司 ID 只能用于可选校验；留空时直接使用 ERP 身份，不能切换租户。
    if requested_company and requested_company != company_id:
        raise HTTPException(status_code=403, detail="company_id 与当前登录用户所属公司不一致")
    # 用户请求里的 permission_tags 不可信，只汇总 ERP 身份接口返回的权限与角色。
    access_tags = _verified_access_tags(user)
    return (
        request,
        company_id,
        # ERP 未返回部门时必须保持为空；Milvus 会因此只允许公共文档，不能信任请求体部门。
        str(user.get("department") or "").strip(),
        access_tags,
    )


def _rag_runtime_config(
    db: Session | None,
    *,
    company_id: str,
    knowledge_base_key: str,
    assistant_key: str,
    knowledge_base_keys: list[str] | tuple[str, ...] = (),
    search_scope: str | None = None,
) -> RagRuntimeConfig:
    """读取数据库中的 RAG 配置，缺少配置时回退到进程默认值。"""
    # 默认 Collection 名称由租户和知识库 key 确定，即使未配置 MySQL 也不会串库。
    # 兼容旧单库参数，同时为无 MySQL 的多库调试调用构造多个稳定 Collection 目标。
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
        # MySQL 只覆盖已配置项，空值继续沿用进程级安全默认值。
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


# 共享辅助函数定义完成后再导入业务路由，避免路由模块引用兼容层时产生循环导入。
from ai_erp_rag_assistant.app.routes import (
    approvals,
    assistants,
    chat as chat_routes,
    rag,
    rag_documents,
    sessions,
    workbench,
)

# 工作流由 chat 模块统一构建；这里仅保留旧的 ``app.api.workflow`` 兼容入口，
# 不重复创建第二份图。
workflow = chat_routes.workflow
stateless_workflow = chat_routes.stateless_workflow

router.include_router(rag_admin_router)
router.include_router(assistants.router)
router.include_router(chat_routes.router)
router.include_router(rag.router)
router.include_router(rag_documents.router)
router.include_router(sessions.router)
router.include_router(approvals.router)
router.include_router(workbench.router)

# 保留历史 ``app.api.<endpoint>`` 导入路径，兼容已有集成代码和测试。
chat = chat_routes.chat
rag_search = rag.rag_search
rag_chat = rag.rag_chat
rag_ingest_text = rag.rag_ingest_text
rag_ingest_pdf = rag.rag_ingest_pdf
rag_ingest_document = rag.rag_ingest_document
_rag_rows_from_text = rag._rag_rows_from_text
_rag_rows_from_pdf = rag._rag_rows_from_pdf
list_rag_documents = rag_documents.list_rag_documents
delete_rag_document = rag_documents.delete_rag_document
update_rag_document_status = rag_documents.update_rag_document_status
session_list = sessions.session_list
session_messages = sessions.session_messages
approval_templates = approvals.approval_templates
approval_form_schema = approvals.approval_form_schema
approval_field_options = approvals.approval_field_options
workbench_summary = workbench.workbench_summary

"""知识库文档列表和删除接口。"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.concurrency import run_in_threadpool

from ai_erp_rag_assistant.app import api as api_module
from ai_erp_rag_assistant.app.database import get_optional_db_session
from ai_erp_rag_assistant.app.routes import rag as rag_module
from ai_erp_rag_assistant.app.schemas import (
    RagDocumentDeleteRequest,
    RagDocumentDeleteResponse,
    RagDocumentListRequest,
    RagDocumentListResponse,
    RagDocumentStatusRequest,
    RagDocumentStatusResponse,
)
from ai_erp_rag_assistant.app.rag_admin_repository import RagAdminRepository


router = APIRouter(tags=["RAG Documents"])


@router.post("/rag/documents/list", response_model=RagDocumentListResponse)
async def list_rag_documents(
    request: RagDocumentListRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagDocumentListResponse:
    """在当前用户可见范围内聚合并分页返回知识库文档。"""
    # 文档管理复用检索 ACL，普通用户无法通过列表观察不可见文档。
    request, company_id, department, access_tags = api_module._rag_identity(
        request, authorization, uid
    )
    runtime = api_module._rag_runtime_config(
        db,
        company_id=company_id,
        knowledge_base_key=request.knowledge_base_key.strip(),
        assistant_key="",
    )
    try:
        if runtime.knowledge_bases and any(
            target.document_scope_loaded for target in runtime.knowledge_bases
        ):
            targets = []
            for target in runtime.knowledge_bases:
                try:
                    target.require_access(
                        department=department,
                        permission_tags=access_tags,
                        action="read",
                    )
                except PermissionError:
                    continue
                targets.append(
                    {
                        "knowledge_base_key": target.knowledge_base_key,
                        "knowledge_base_name": target.knowledge_base_name,
                        "collection": target.collection,
                        "active_documents": target.active_documents,
                        "document_scope_loaded": target.document_scope_loaded,
                    }
                )
            if not targets and runtime.knowledge_bases:
                raise PermissionError("当前用户无权访问可用知识库")
            # 多知识库列表统一分页，并保留每个文件所属知识库。
            items, total = await run_in_threadpool(
                api_module.milvus_service.list_documents_many,
                company_id=company_id,
                department=department,
                permission_tags=access_tags,
                targets=targets,
                keyword=request.keyword,
                page=request.page,
                page_size=request.page_size,
            )
        else:
            runtime.require_access(
                department=department, permission_tags=access_tags, action="read"
            )
            # Milvus 查询为阻塞操作；服务层按 source + version 聚合后再分页。
            items, total = await run_in_threadpool(
                api_module.milvus_service.list_documents,
                company_id=company_id,
                department=department,
                permission_tags=access_tags,
                collection_name=runtime.collection,
                knowledge_base_key=request.knowledge_base_key.strip(),
                keyword=request.keyword,
                page=request.page,
                page_size=request.page_size,
            )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    # 响应中的知识库名称必须沿用上面的 ACL 过滤，不能泄露未授权知识库元数据。
    response_key, response_keys, searched, response_collection, response_collections = (
        rag_module._runtime_source_fields(
            runtime,
            request.knowledge_base_key.strip(),
            department=department,
            access_tags=access_tags,
        )
    )
    return RagDocumentListResponse(
        items=items,
        count=len(items),
        total=total,
        page=request.page,
        page_size=request.page_size,
        company_id=company_id,
        knowledge_base_key=response_key,
        knowledge_base_keys=response_keys,
        searched_knowledge_bases=searched,
        collection=response_collection,
        collections=response_collections,
    )


@router.post("/rag/documents/delete", response_model=RagDocumentDeleteResponse)
async def delete_rag_document(
    request: RagDocumentDeleteRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagDocumentDeleteResponse:
    """按租户、可见范围、来源和版本精确删除文档 Chunk。"""
    # 先解析可信 ACL，再把同一过滤条件同时用于存在性检查和删除。
    request, company_id, department, access_tags = api_module._rag_identity(
        request, authorization, uid
    )
    runtime = api_module._rag_runtime_config(
        db,
        company_id=company_id,
        knowledge_base_key=request.knowledge_base_key.strip(),
        assistant_key="",
    )
    try:
        runtime.require_access(
            department=department, permission_tags=access_tags, action="delete"
        )
        # 必须携带精确 source + version，服务层不会执行模糊或批量删除。
        deleted = await run_in_threadpool(
            api_module.milvus_service.delete_document,
            company_id=company_id,
            source=request.source,
            version=request.version,
            department=department,
            permission_tags=access_tags,
            collection_name=runtime.collection,
            knowledge_base_key=request.knowledge_base_key.strip(),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    if not deleted:
        raise HTTPException(status_code=404, detail="文档不存在或当前用户无权删除")
    return RagDocumentDeleteResponse(
        source=request.source.strip(),
        version=request.version.strip(),
        deleted_chunk_count=deleted,
        company_id=company_id,
        knowledge_base_key=request.knowledge_base_key.strip(),
        collection=runtime.collection,
    )


@router.post("/rag/documents/status", response_model=RagDocumentStatusResponse)
def update_rag_document_status(
    request: RagDocumentStatusRequest,
    db: Annotated[Session | None, Depends(get_optional_db_session)] = None,
    authorization: str | None = Header(default=None),
    uid: str | None = Header(default=None, alias="UID"),
) -> RagDocumentStatusResponse:
    """启用或停用文件检索；停用只影响召回，不删除文件和向量。"""
    request, company_id, department, access_tags = api_module._rag_identity(
        request, authorization, uid
    )
    if db is None:
        raise HTTPException(status_code=503, detail="未配置 MySQL，无法修改文件检索状态")
    knowledge_key = request.knowledge_base_key.strip()
    runtime = api_module._rag_runtime_config(
        db,
        company_id=company_id,
        knowledge_base_key=knowledge_key,
        assistant_key="",
    )
    try:
        target = next(
            (item for item in runtime.knowledge_bases if item.knowledge_base_key == knowledge_key),
            None,
        )
        if target is not None:
            target.require_access(
                department=department,
                permission_tags=access_tags,
                action="write",
            )
        else:
            runtime.require_access(
                department=department,
                permission_tags=access_tags,
                action="write",
            )
        updated = RagAdminRepository(db).set_document_search_enabled(
            company_id,
            knowledge_key,
            source=request.source,
            version=request.version,
            enabled=request.enabled,
        )
    except ValueError as exc:
        db.rollback()
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except PermissionError as exc:
        db.rollback()
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except LookupError as exc:
        db.rollback()
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise HTTPException(status_code=503, detail="MySQL 修改文件状态失败") from exc
    return RagDocumentStatusResponse(
        source=request.source.strip(),
        version=request.version.strip(),
        enabled=request.enabled,
        updated_count=updated,
        company_id=company_id,
        knowledge_base_key=knowledge_key,
    )

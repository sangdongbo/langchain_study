"""FastAPI 应用入口和不触发外部连接的健康检查。"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import FastAPI, Request
from fastapi.exception_handlers import http_exception_handler
from starlette.exceptions import HTTPException as StarletteHTTPException
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import JSONResponse, Response

from ai_erp_rag_assistant.app.api import router
from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.database import mysql_configured
from ai_erp_rag_assistant.app.services.audit_log_service import write_audit_event


PUBLIC_SERVER_ERROR = "服务暂时不可用，请稍后重试"


app = FastAPI(
    title="AI ERP RAG Assistant",
    description="Enterprise RAG, ERP tools and LangGraph approval workflows.",
)
# 统一处理浏览器跨域预检；业务路由不需要重复声明 OPTIONS。
# 生产环境通过 AI_ERP_CORS_ORIGINS 指定前端域名，不能依赖通配符放开来源。
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins,
    # 本地联调前端端口经常变化；仅放开回环地址，外部域名仍必须列入配置。
    allow_origin_regex=r"^https?://(localhost|127\.0\.0\.1)(:\d+)?$",
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    # Header 名由前端网关和不同助手能力共同扩展。来源仍受上面的白名单约束，
    # 因此这里回显浏览器声明的请求头，避免 /api/chat 因新增 Header 预检失败。
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
    max_age=600,
)
app.include_router(router)


def _public_server_error_detail(detail: Any) -> Any:
    """隐藏底层异常，同时保留导入任务等结构化补偿字段。"""
    if not isinstance(detail, dict):
        return PUBLIC_SERVER_ERROR
    safe_detail = dict(detail)
    for key in ("message", "error_message"):
        if key in safe_detail:
            safe_detail[key] = PUBLIC_SERVER_ERROR
    return safe_detail


@app.exception_handler(StarletteHTTPException)
async def safe_http_exception_handler(
    request: Request,
    exc: StarletteHTTPException,
) -> Response:
    """5xx 仅返回稳定公开文案，原始原因写入脱敏审计日志。"""
    # 没有 cause 的 5xx 是代码主动给出的配置提示；保留它们帮助部署排障。
    if exc.status_code < 500 or exc.__cause__ is None:
        return await http_exception_handler(request, exc)
    cause = exc.__cause__
    try:
        write_audit_event(
            "http.server_error",
            {
                "method": request.method,
                "path": request.url.path,
                "status_code": exc.status_code,
                "error": str(cause)[:300],
            },
        )
    except Exception:
        # 错误响应不能再被审计文件故障打断；应用日志仍会记录原异常链。
        pass
    public_exception = StarletteHTTPException(
        status_code=exc.status_code,
        detail=_public_server_error_detail(exc.detail),
        headers=exc.headers,
    )
    return await http_exception_handler(request, public_exception)


@app.exception_handler(Exception)
async def safe_unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """把未处理异常转换为可追踪且不泄露内部细节的 JSON 响应。"""
    request_id = uuid4().hex
    try:
        write_audit_event(
            "http.unhandled_error",
            {
                "request_id": request_id,
                "method": request.method,
                "path": request.url.path,
                "error_type": type(exc).__name__,
                "error": str(exc)[:300],
            },
        )
    except Exception:
        # 审计存储故障不能覆盖原始错误响应。
        pass
    return JSONResponse(
        status_code=500,
        content={"detail": PUBLIC_SERVER_ERROR, "request_id": request_id},
        headers={"X-Request-ID": request_id},
    )


@app.get("/health")
def health() -> dict[str, str]:
    """返回各组件是否已配置，不验证或暴露真实凭据。"""
    settings = get_settings()
    return {
        "status": "ok",
        # 健康检查是公开端点，只返回配置状态，不暴露内网地址和资源名称。
        "milvus_configured": str(
            bool(settings.milvus_uri and settings.milvus_collection)
        ).lower(),
        "erp_mode": settings.erp_mode,
        "erp_read_mode": settings.erp_read_mode,
        "erp_write_mode": settings.erp_write_mode,
        "erp_skip_userinfo_validation": str(settings.erp_skip_userinfo_validation).lower(),
        "session_store": settings.session_store,
        "session_store_configured": str(
            settings.session_store != "mysql"
            or bool(settings.mysql_database and settings.mysql_user)
        ).lower(),
        # 这里只报告配置条件；运行表是否已由 DBA 创建通过实际请求或状态接口验证。
        "erp_durable_execution_configured": str(
            settings.session_store == "mysql"
            and bool(settings.mysql_database and settings.mysql_user)
        ).lower(),
        "llm_configured": str(bool(settings.llm_api_key)).lower(),
        "embedding_configured": str(bool(settings.embedding_api_key)).lower(),
        "mysql_configured": str(mysql_configured(settings)).lower(),
        "langsmith_tracing": str(settings.langsmith_tracing).lower(),
        "langsmith_configured": str(bool(settings.langsmith_api_key)).lower(),
        "langsmith_endpoint_configured": str(bool(settings.langsmith_endpoint)).lower(),
        "langsmith_workspace_configured": str(
            bool(settings.langsmith_workspace_id)
        ).lower(),
    }

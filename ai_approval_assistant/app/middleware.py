from __future__ import annotations
import logging
import time
from collections.abc import Callable, Awaitable
from fastapi import Request, Response

logger = logging.getLogger("ai_approval_assistant.http")


async def request_log_middleware(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    """记录每个 HTTP 请求的方法、路径、状态码和耗时。"""
    started_at = time.perf_counter()
    response = await call_next(request)
    duration_ms = (time.perf_counter() - started_at) * 1000
    logger.info(
        "%s %s -> %s %.2fms",
        request.method,
        request.url.path,
        response.status_code,
        duration_ms,
    )
    return response

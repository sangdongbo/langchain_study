"""集中管理 LangSmith Trace 客户端和敏感字段脱敏。"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

import langsmith.anonymizer as langsmith_anonymizer
from langsmith import Client

from ai_erp_rag_assistant.app.config import get_settings
from ai_erp_rag_assistant.app.services.sensitive_data import is_sensitive_field_name


def _identity(data: Any) -> Any:
    return data


# 旧版 LangSmith 没有 create_secret_anonymizer 时仍执行字段级脱敏。
_secret_factory: Any = getattr(langsmith_anonymizer, "create_secret_anonymizer", None)
_secret_anonymizer = _secret_factory() if callable(_secret_factory) else _identity
_field_anonymizer = langsmith_anonymizer.create_anonymizer(
    lambda value, path: (
        "[REDACTED]"
        if path and is_sensitive_field_name(path[-1])
        else value
    ),
    max_depth=24,
)


def anonymize_trace(data: Any) -> Any:
    """在 Trace 离开服务进程前清理密钥和登录凭据。"""
    return _field_anonymizer(_secret_anonymizer(data))


@lru_cache(maxsize=1)
def langsmith_client() -> Client | None:
    """按部署配置创建统一的 LangSmith 客户端；未启用时返回 None。"""
    settings = get_settings()
    if not settings.langsmith_tracing or not settings.langsmith_api_key:
        return None
    return Client(
        api_url=settings.langsmith_endpoint or None,
        api_key=settings.langsmith_api_key,
        workspace_id=settings.langsmith_workspace_id or None,
        anonymizer=anonymize_trace,
    )

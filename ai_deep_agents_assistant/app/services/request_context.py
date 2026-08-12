from __future__ import annotations

from contextvars import ContextVar, Token
from dataclasses import dataclass


@dataclass(frozen=True)
class ErpRequestContext:
    user_id: str
    uid: str
    authorization: str


_erp_request_context: ContextVar[ErpRequestContext | None] = ContextVar(
    "erp_request_context",
    default=None,
)


def set_erp_request_context(
    user_id: str,
    uid: str | None,
    authorization: str | None,
) -> Token[ErpRequestContext | None]:
    return _erp_request_context.set(
        ErpRequestContext(
            user_id=user_id,
            uid=str(uid or ""),
            authorization=str(authorization or ""),
        )
    )


def reset_erp_request_context(token: Token[ErpRequestContext | None]) -> None:
    _erp_request_context.reset(token)


def get_erp_request_context() -> ErpRequestContext:
    context = _erp_request_context.get()
    if context is None:
        raise RuntimeError("ERP request context is not available")
    if not context.uid or not context.authorization:
        raise ValueError("真实提交日报需要 ERP UID 和 Authorization。")
    return context

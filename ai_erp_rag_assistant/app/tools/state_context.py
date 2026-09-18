"""State 工具共用的服务端身份读取规则。"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any


def verified_user_context(state: Mapping[str, Any]) -> dict[str, Any]:
    """读取已经由 ERP 校验的用户上下文。

    State 工具不从请求级 ``company_id``、``department`` 或 ``permission_tags``
    推断权限。缺少服务端注入的 ``user_context`` 时直接拒绝，避免工具被模型或
    前端传入的伪造租户边界驱动。
    """
    raw_user = state.get("user_context")
    if not isinstance(raw_user, Mapping):
        raise PermissionError("State 缺少已验证的 user_context")
    user = dict(raw_user)
    if not str(user.get("company_id") or "").strip():
        raise PermissionError("当前用户没有可用的 company_id")
    return user


def verified_permission_tags(user: Mapping[str, Any]) -> list[str]:
    """只从 ERP 身份上下文整理 RAG 权限标签。"""
    raw_values = user.get("rag_access_tags")
    if not raw_values:
        for key in ("permissions", "permission_tags", "roles"):
            candidate = user.get(key)
            if candidate:
                raw_values = candidate
                break
    if isinstance(raw_values, str):
        raw_values = raw_values.split(",")
    if not isinstance(raw_values, (list, tuple, set)):
        return []
    return sorted({str(item).strip() for item in raw_values if str(item).strip()})


"""统一识别凭据字段，避免日志、Trace 和管理配置使用不同规则。"""

from __future__ import annotations


_SENSITIVE_SUFFIXES = (
    "authorization",
    "apikey",
    "cookie",
    "password",
    "secret",
    "token",
)


def is_sensitive_field_name(name: object) -> bool:
    """识别 snake_case、kebab-case 和 camelCase 形式的凭据键名。"""
    normalized = "".join(character for character in str(name).casefold() if character.isalnum())
    return any(normalized.endswith(suffix) for suffix in _SENSITIVE_SUFFIXES)

from __future__ import annotations

import json
import logging
from pathlib import Path
from threading import Lock
from typing import Any

from ai_erp_rag_assistant.app.config import get_settings


logger = logging.getLogger("ai_erp_rag_assistant.audit")
_file_lock = Lock()

_SECRET_KEYS = {
    "authorization",
    "cookie",
    "password",
    "refresh_token",
    "secret",
    "token",
}
_VALUE_CONTAINER_KEYS = {"fields", "form_data", "form_value", "submission_fields", "values"}


def write_audit_event(event: str, payload: dict[str, Any]) -> None:
    """Write one JSON audit event after removing credentials and form values."""
    sanitized = sanitize_for_log(payload)
    logger.info(
        "%s %s",
        event,
        json.dumps(sanitized, ensure_ascii=False, default=str),
    )
    path = get_settings().audit_log_path.strip()
    if path:
        log_path = Path(path)
        if not log_path.is_absolute():
            log_path = Path(__file__).resolve().parents[2] / log_path
        log_path.parent.mkdir(parents=True, exist_ok=True)
        record = {
            "event": event,
            "payload": sanitized,
        }
        with _file_lock:
            with log_path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")


def sanitize_for_log(value: Any, *, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        if parent_key.lower() in _VALUE_CONTAINER_KEYS:
            return {"field_keys": [str(key) for key in value.keys()], "field_count": len(value)}
        result: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower()
            if normalized_key in _SECRET_KEYS:
                result[str(key)] = "[REDACTED]"
            elif normalized_key == "body" and isinstance(item, dict):
                result[str(key)] = summarize_request_body(item)
            else:
                result[str(key)] = sanitize_for_log(item, parent_key=normalized_key)
        return result
    if isinstance(value, list):
        return [sanitize_for_log(item, parent_key=parent_key) for item in value[:20]]
    return value


def summarize_request_body(body: dict[str, Any]) -> dict[str, Any]:
    """Retain routing metadata and field names, never personal form contents."""
    summary: dict[str, Any] = {}
    for key, value in body.items():
        normalized_key = str(key).lower()
        if normalized_key in _VALUE_CONTAINER_KEYS:
            if isinstance(value, dict):
                summary[str(key)] = {
                    "field_keys": [str(field_key) for field_key in value],
                    "field_count": len(value),
                }
            elif isinstance(value, list):
                summary[str(key)] = {
                    "field_keys": [
                        str(item.get("field_key"))
                        for item in value
                        if isinstance(item, dict) and item.get("field_key")
                    ],
                    "field_count": len(value),
                }
            continue
        if normalized_key == "node_list" and isinstance(value, list):
            summary[str(key)] = {
                "node_ids": [str(item.get("id") or "") for item in value if isinstance(item, dict)],
                "node_count": len(value),
            }
            continue
        summary[str(key)] = sanitize_for_log(value, parent_key=normalized_key)
    return summary


def summarize_response(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    result: dict[str, Any] = {
        "code": payload.get("code"),
        "message": payload.get("message"),
        "data_type": type(data).__name__,
    }
    if isinstance(data, list):
        result["data_count"] = len(data)
    elif isinstance(data, dict):
        result["data_keys"] = list(data.keys())[:30]
    return result

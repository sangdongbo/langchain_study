from __future__ import annotations

from datetime import date
from html import unescape
import re
from typing import Any

from app.schemas.approval import UserContext
from app.schemas.daily_report import DailyReportContext, DailyReportSubmitResult
from app.services.daily_report_api_client import DailyReportApiClient


class DailyReportSubmitError(ValueError):
    """日报提交被 ERP 业务校验拒绝。"""


class DailyReportService:
    """写日志业务服务。"""

    def __init__(self, api_client: DailyReportApiClient | None = None) -> None:
        self._api_client = api_client or DailyReportApiClient()

    def load_context(
        self, user: UserContext, report_type: int = 1, report_date: str | None = None
    ) -> DailyReportContext:
        selected_date = report_date or date.today().isoformat()
        form_fields_payload = self._api_client.get_form_fields(user)
        config_payload = self._api_client.get_config(user)
        draft_payload = self._api_client.get_draft(user, report_type, selected_date)
        config = _payload_data_dict(config_payload)
        draft = _payload_data_dict(draft_payload)
        if _should_initialize_draft_recipients(draft, config):
            self._api_client.set_draft(
                user,
                _draft_set_payload(report_type, selected_date, config),
            )
            draft_payload = self._api_client.get_draft(user, report_type, selected_date)
            draft = _payload_data_dict(draft_payload)
        sync_payload = self._api_client.sync_data(user, report_type, selected_date)
        sync_data = sync_payload.get("data")
        default_payload = _default_add_payload(
            report_type=report_type,
            report_date=selected_date,
            draft=draft,
            config=config,
            form_fields_payload=form_fields_payload,
            sync_data=sync_data,
        )
        return DailyReportContext(
            report_type=report_type,
            report_date=selected_date,
            form_fields_payload=form_fields_payload,
            config=config,
            draft=draft,
            sync_data=sync_data,
            default_payload=default_payload,
        )

    def payload_from_form_answer(self, answer: dict[str, Any] | None) -> dict[str, Any]:
        if not isinstance(answer, dict) or answer.get("field_key") != "__daily_report_form__":
            raise ValueError("daily report form answer is required")
        value = answer.get("value")
        if not isinstance(value, dict):
            raise ValueError("daily report form value must be an object")
        self.validate_payload(value)
        return value

    def preview_from_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        self.validate_payload(payload)
        return {
            "report_type": payload.get("type", 1),
            "date": payload.get("date"),
            "content": _plain_text(payload.get("content", "")),
            "fields": _preview_fields(
                payload.get("extends") or {},
                payload.get("extend_fields") or [],
            ),
            "recipients": payload.get("recipients") or [],
            "cc_recipients": payload.get("cc_recipients") or [],
            "sync_summary": None,
        }

    def save_draft_payload(
        self, user: UserContext, payload: dict[str, Any]
    ) -> dict[str, Any]:
        """保存日报草稿，保持和 ERP 写日志弹窗自动保存接口一致。"""
        self.validate_payload(payload)
        return self._api_client.set_draft(user, _draft_save_payload(payload))

    def submit_payload(
        self, user: UserContext, payload: dict[str, Any]
    ) -> DailyReportSubmitResult:
        self.validate_payload(payload)
        response = self._api_client.add_daily_report(user, payload)
        if response.get("code") != 200:
            message = str(response.get("message") or response.get("msg") or "提交失败")
            raise DailyReportSubmitError(message)
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        report_id = data.get("id") or data.get("report_id") or data.get("request_id")
        return DailyReportSubmitResult(
            report_id=str(report_id) if report_id is not None else None,
            status=str(data.get("status") or "submitted"),
            raw_data=data,
        )

    def validate_payload(self, payload: dict[str, Any]) -> None:
        if not str(payload.get("content") or "").strip():
            raise ValueError("daily report content is required")
        if not isinstance(payload.get("extends"), dict):
            raise ValueError("daily report extends must be an object")
        if not isinstance(payload.get("extend_fields"), list):
            raise ValueError("daily report extend_fields must be a list")


def _default_add_payload(
    report_type: int,
    report_date: str,
    draft: dict[str, Any],
    config: dict[str, Any],
    form_fields_payload: dict[str, Any],
    sync_data: Any = None,
) -> dict[str, Any]:
    content = str(draft.get("content") or "")
    if not content.strip():
        content = _content_from_sync_data(sync_data)
    return {
        "type": report_type,
        "date": report_date,
        "content": content,
        "files": draft.get("files") if isinstance(draft.get("files"), list) else [],
        "at_uids": draft.get("at_uids") if isinstance(draft.get("at_uids"), list) else [],
        "recipients": _list_from(draft, config, "recipients", "parse_recipients"),
        "cc_recipients": _list_from(
            draft, config, "cc_recipients", "parse_cc_recipients"
        ),
        "extends": draft.get("extends") if isinstance(draft.get("extends"), dict) else {},
        "extend_fields": _form_fields(form_fields_payload),
    }


def _should_initialize_draft_recipients(
    draft: dict[str, Any], config: dict[str, Any]
) -> bool:
    if _list_from(draft, {}, "recipients") or _list_from(draft, {}, "cc_recipients"):
        return False
    return bool(
        _list_from(config, {}, "parse_recipients")
        or _list_from(config, {}, "parse_cc_recipients")
    )


def _draft_set_payload(
    report_type: int, report_date: str, config: dict[str, Any]
) -> dict[str, Any]:
    return {
        "data": {
            "type": report_type,
            "date": report_date,
            "recipients": _list_from(config, {}, "parse_recipients"),
            "cc_recipients": _list_from(config, {}, "parse_cc_recipients"),
        }
    }


def _draft_save_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "data": {
            "type": payload.get("type", 1),
            "date": payload.get("date"),
            "content": payload.get("content", ""),
            "files": payload.get("files") if isinstance(payload.get("files"), list) else [],
            "at_uids": payload.get("at_uids") if isinstance(payload.get("at_uids"), list) else [],
            "recipients": payload.get("recipients") if isinstance(payload.get("recipients"), list) else [],
            "cc_recipients": payload.get("cc_recipients")
            if isinstance(payload.get("cc_recipients"), list)
            else [],
            "extends": payload.get("extends") if isinstance(payload.get("extends"), dict) else {},
        }
    }


def _payload_data_dict(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _list_from(
    primary: dict[str, Any],
    fallback: dict[str, Any],
    key: str,
    fallback_key: str | None = None,
) -> list[dict[str, Any]]:
    for source, source_key in (
        (primary, key),
        (fallback, fallback_key or key),
        (fallback, key),
    ):
        value = source.get(source_key)
        if isinstance(value, list):
            items = [item for item in value if isinstance(item, dict)]
            if items:
                return items
    return []


def _form_fields(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return _custom_form_fields(data)
    if isinstance(data, dict):
        for key in ("fields", "list", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return _custom_form_fields(value)
    return []


def _custom_form_fields(fields: list[Any]) -> list[dict[str, Any]]:
    return [
        item
        for item in fields
        if isinstance(item, dict)
        and item.get("field_key") != "content"
        and not bool(item.get("is_system"))
    ]


def _content_from_sync_data(sync_data: Any) -> str:
    if not isinstance(sync_data, list):
        return ""
    lines = []
    for index, item in enumerate(sync_data, start=1):
        text = _sync_item_text(item)
        if text:
            lines.append(f"{index}. {text}")
    return "\n".join(lines)


def _sync_item_text(item: Any) -> str:
    if isinstance(item, str):
        return item.strip()
    if not isinstance(item, dict):
        return ""
    parts = []
    for key in (
        "title",
        "content",
        "name",
        "customer_name",
        "followup_content",
        "process_name",
        "order_no",
        "work_ticket_no",
    ):
        value = item.get(key)
        if value is not None and str(value).strip():
            parts.append(str(value).strip())
    return " - ".join(dict.fromkeys(parts))


def _preview_fields(
    extends: dict[str, Any], extend_fields: list[Any] | None = None
) -> list[dict[str, str]]:
    labels = _extend_field_labels(extend_fields or [])
    fields: list[dict[str, str]] = []
    for key, value in extends.items():
        if isinstance(value, dict):
            raw = value.get("text") if value.get("text") is not None else value.get("value")
        else:
            raw = value
        text = _plain_text(raw)
        if text:
            fields.append({"name": key, "label": labels.get(key, key), "value": text})
    return fields


def _extend_field_labels(fields: list[Any]) -> dict[str, str]:
    labels: dict[str, str] = {}
    for field in fields:
        if not isinstance(field, dict):
            continue
        key = field.get("field_key") or field.get("name") or field.get("field")
        label = field.get("field_name") or field.get("label") or key
        if key:
            labels[str(key)] = str(label)
    return labels


def _plain_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return "，".join(_plain_text(item) for item in value if _plain_text(item))
    text = str(value)
    text = re.sub(r"<br\s*/?>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"</(div|p|li|tr)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = unescape(text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


daily_report_service = DailyReportService()

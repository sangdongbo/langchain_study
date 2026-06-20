from __future__ import annotations

from datetime import date
from typing import Any

from app.schemas.approval import UserContext
from app.schemas.daily_report import DailyReportContext, DailyReportSubmitResult
from app.services.daily_report_api_client import DailyReportApiClient


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
        sync_payload = self._api_client.sync_data(user, report_type, selected_date)
        config = _payload_data_dict(config_payload)
        draft = _payload_data_dict(draft_payload)
        default_payload = _default_add_payload(
            report_type=report_type,
            report_date=selected_date,
            draft=draft,
            config=config,
            form_fields_payload=form_fields_payload,
        )
        return DailyReportContext(
            report_type=report_type,
            report_date=selected_date,
            form_fields_payload=form_fields_payload,
            config=config,
            draft=draft,
            sync_data=sync_payload.get("data"),
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
            "content": payload.get("content", ""),
            "fields": _preview_fields(payload.get("extends") or {}),
            "recipients": payload.get("recipients") or [],
            "cc_recipients": payload.get("cc_recipients") or [],
            "sync_summary": None,
        }

    def submit_payload(
        self, user: UserContext, payload: dict[str, Any]
    ) -> DailyReportSubmitResult:
        self.validate_payload(payload)
        response = self._api_client.add_daily_report(user, payload)
        if response.get("code") != 200:
            raise ValueError(f"daily report add returned code {response.get('code')}")
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
) -> dict[str, Any]:
    return {
        "type": report_type,
        "date": report_date,
        "content": str(draft.get("content") or ""),
        "files": draft.get("files") if isinstance(draft.get("files"), list) else [],
        "at_uids": draft.get("at_uids") if isinstance(draft.get("at_uids"), list) else [],
        "recipients": _list_from(draft, config, "recipients"),
        "cc_recipients": _list_from(draft, config, "cc_recipients"),
        "extends": draft.get("extends") if isinstance(draft.get("extends"), dict) else {},
        "extend_fields": _form_fields(form_fields_payload),
    }


def _payload_data_dict(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    return data if isinstance(data, dict) else {}


def _list_from(
    primary: dict[str, Any], fallback: dict[str, Any], key: str
) -> list[dict[str, Any]]:
    for source in (primary, fallback):
        value = source.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _form_fields(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data")
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        for key in ("fields", "list", "data"):
            value = data.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    return []


def _preview_fields(extends: dict[str, Any]) -> list[dict[str, str]]:
    fields: list[dict[str, str]] = []
    for key, value in extends.items():
        if isinstance(value, dict):
            raw = value.get("text") if value.get("text") is not None else value.get("value")
        else:
            raw = value
        fields.append({"name": key, "label": key, "value": str(raw or "")})
    return fields


daily_report_service = DailyReportService()

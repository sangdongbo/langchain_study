from __future__ import annotations

import re
from copy import deepcopy
from datetime import date
from typing import Any

from ai_deep_agents_assistant.app.schemas.daily_report import (
    DailyReportDraft,
    DailyReportPreview,
    DailyReportSubmitResult,
)
from ai_deep_agents_assistant.app.services.daily_report_api_client import (
    DailyReportApiClient,
)
from ai_deep_agents_assistant.app.services.request_context import ErpRequestContext


class DailyReportSubmitError(ValueError):
    """ERP rejected the daily report submission."""


class DailyReportService:
    """Deterministic daily report rules backed by real ERP endpoints."""

    def __init__(self, api_client: DailyReportApiClient | None = None) -> None:
        self._api_client = api_client or DailyReportApiClient()

    def current_date(self) -> str:
        return date.today().isoformat()

    def build_draft(
        self,
        message: str,
        existing_payload: dict[str, Any] | None = None,
        user: ErpRequestContext | None = None,
    ) -> DailyReportDraft:
        payload = deepcopy(existing_payload or {})
        payload.setdefault("type", 1)
        extracted_date = self._extract_date(message)
        if extracted_date:
            payload["date"] = extracted_date
        payload.setdefault("date", self.current_date())

        if user is not None and not existing_payload:
            payload = self._load_erp_payload(
                user,
                report_type=int(payload.get("type") or 1),
                report_date=str(payload.get("date") or self.current_date()),
            )

        content = self._extract_content(message)
        if content:
            payload["content"] = content

        missing_fields = []
        if not str(payload.get("date") or "").strip():
            missing_fields.append("date")
        if not str(payload.get("content") or "").strip():
            missing_fields.append("content")

        if missing_fields:
            question = (
                "请补充日报日期，格式为 YYYY-MM-DD。"
                if missing_fields[0] == "date"
                else "请补充今天完成的工作内容。"
            )
            return DailyReportDraft(
                payload=payload,
                missing_fields=missing_fields,
                next_question=question,
            )

        preview = self.build_preview(payload)
        return DailyReportDraft(
            payload=payload,
            next_question=(
                "日报预览已生成。提交操作受人工确认保护，请继续发起提交确认。"
            ),
            preview=preview,
        )

    def build_preview(self, payload: dict[str, Any]) -> DailyReportPreview:
        self._validate_erp_payload(payload)
        report_date = str(payload.get("date") or "").strip()
        content = str(payload.get("content") or "").strip()
        if not report_date:
            raise ValueError("日报日期不能为空。")
        if not content:
            raise ValueError("日报工作内容不能为空。")
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", report_date):
            raise ValueError("日报日期格式必须为 YYYY-MM-DD。")
        return DailyReportPreview(
            report_type=int(payload.get("type") or 1),
            date=report_date,
            content=content,
        )

    def submit(
        self,
        payload: dict[str, Any],
        user: ErpRequestContext,
    ) -> DailyReportSubmitResult:
        self.build_preview(payload)
        response = self._api_client.add_daily_report(user, payload)
        if response.get("code") != 200:
            message = str(response.get("message") or response.get("msg") or "提交失败")
            raise DailyReportSubmitError(message)
        data = response.get("data") if isinstance(response.get("data"), dict) else {}
        request_id = data.get("id") or data.get("report_id") or data.get("request_id")
        return DailyReportSubmitResult(
            request_id=str(request_id) if request_id is not None else None,
            raw_data=data,
        )

    def _load_erp_payload(
        self,
        user: ErpRequestContext,
        report_type: int,
        report_date: str,
    ) -> dict[str, Any]:
        form_fields_payload = self._api_client.get_form_fields(user)
        config = self._payload_data_dict(self._api_client.get_config(user))
        draft = self._payload_data_dict(
            self._api_client.get_draft(user, report_type, report_date)
        )
        sync_payload = self._api_client.sync_data(user, report_type, report_date)
        content = str(draft.get("content") or "")
        if not content.strip():
            content = self._content_from_sync_data(sync_payload.get("data"))
        return {
            "type": report_type,
            "date": report_date,
            "content": content,
            "files": draft.get("files") if isinstance(draft.get("files"), list) else [],
            "at_uids": draft.get("at_uids")
            if isinstance(draft.get("at_uids"), list)
            else [],
            "recipients": self._list_from(draft, config, "recipients", "parse_recipients"),
            "cc_recipients": self._list_from(
                draft,
                config,
                "cc_recipients",
                "parse_cc_recipients",
            ),
            "extends": draft.get("extends")
            if isinstance(draft.get("extends"), dict)
            else {},
            "extend_fields": self._form_fields(form_fields_payload),
        }

    def _extract_date(self, message: str) -> str:
        match = re.search(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)", message)
        if match:
            return match.group(1)
        if "今天" in message or "今日" in message:
            return self.current_date()
        return ""

    def _extract_content(self, message: str) -> str:
        content = message.strip()
        if ("日报" in content or "日志" in content) and re.search(r"[：:]", content):
            content = re.split(r"[：:]", content, maxsplit=1)[1].strip()
            return content
        content = re.sub(
            r"^(请|帮我|请帮我|用\S*agent帮我|用\S*agent)?\s*(写|填写|创建|生成)?\s*(今天|今日)?\s*(的)?\s*(日报|日志)\s*[：:，,]?\s*",
            "",
            content,
            flags=re.IGNORECASE,
        ).strip()
        content = re.sub(r"^\d{4}-\d{2}-\d{2}\s*[：:，,]?\s*", "", content).strip()
        if content in {"", "写日报", "写日志", "日报", "日志"}:
            return ""
        return content

    def _payload_data_dict(self, payload: dict[str, Any]) -> dict[str, Any]:
        data = payload.get("data")
        return data if isinstance(data, dict) else {}

    def _list_from(
        self,
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

    def _form_fields(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        data = payload.get("data")
        if isinstance(data, list):
            fields = data
        elif isinstance(data, dict):
            fields = []
            for key in ("fields", "list", "data"):
                value = data.get(key)
                if isinstance(value, list):
                    fields = value
                    break
        else:
            fields = []
        return [
            item
            for item in fields
            if isinstance(item, dict)
            and item.get("field_key") != "content"
            and not bool(item.get("is_system"))
        ]

    def _content_from_sync_data(self, sync_data: Any) -> str:
        if not isinstance(sync_data, list):
            return ""
        lines = []
        for index, item in enumerate(sync_data, start=1):
            if isinstance(item, str):
                text = item.strip()
            elif isinstance(item, dict):
                text = " - ".join(
                    str(item[key]).strip()
                    for key in ("title", "content", "name", "customer_name")
                    if item.get(key) is not None and str(item[key]).strip()
                )
            else:
                text = ""
            if text:
                lines.append(f"{index}. {text}")
        return "\n".join(lines)

    def _validate_erp_payload(self, payload: dict[str, Any]) -> None:
        required_types = {
            "files": list,
            "at_uids": list,
            "recipients": list,
            "cc_recipients": list,
            "extends": dict,
            "extend_fields": list,
        }
        for key, expected_type in required_types.items():
            if not isinstance(payload.get(key), expected_type):
                raise ValueError(f"日报 payload 字段 {key} 格式错误。")


daily_report_service = DailyReportService()

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DailyReportPreview(BaseModel):
    """Human-readable daily report preview."""

    report_type: int = 1
    date: str
    content: str


class DailyReportDraft(BaseModel):
    """Deterministic draft returned to the Deep Agent."""

    payload: dict[str, object] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    next_question: str
    preview: DailyReportPreview | None = None


class DailyReportSubmitResult(BaseModel):
    """ERP daily report submission result."""

    request_id: str | None = None
    status: Literal["submitted"] = "submitted"
    raw_data: dict[str, Any] = Field(default_factory=dict)

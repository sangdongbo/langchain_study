from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class DailyReportPreview(BaseModel):
    """供人工阅读的日报预览。"""

    report_type: int = 1
    date: str
    content: str


class DailyReportDraft(BaseModel):
    """返回给 Deep Agent 的确定性草稿。"""

    payload: dict[str, object] = Field(default_factory=dict)
    missing_fields: list[str] = Field(default_factory=list)
    next_question: str
    preview: DailyReportPreview | None = None


class DailyReportSubmitResult(BaseModel):
    """ERP 日报提交结果。"""

    request_id: str | None = None
    status: Literal["submitted"] = "submitted"
    raw_data: dict[str, Any] = Field(default_factory=dict)

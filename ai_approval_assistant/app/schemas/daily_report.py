from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class DailyReportContext(BaseModel):
    """写日志页面初始化上下文。"""

    report_type: int = 1
    report_date: str
    form_fields_payload: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    draft: dict[str, Any] = Field(default_factory=dict)
    sync_data: dict[str, Any] | list[Any] | None = None
    default_payload: dict[str, Any] = Field(default_factory=dict)


class DailyReportSubmitResult(BaseModel):
    """日报提交结果。"""

    report_id: str | None = None
    status: str = "submitted"
    raw_data: dict[str, Any] = Field(default_factory=dict)

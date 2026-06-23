from __future__ import annotations

from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from app.schemas.approval import UserContext
from app.services.daily_report_service import daily_report_service


# tools 层是 LangGraph/Studio 能看懂的能力边界；具体 ERP 请求仍留在 service/client，
# agent 节点只关心“加载上下文、保存草稿、预览、提交”这些业务动作。
class DailyReportToolUserInput(BaseModel):
    user_id: str = Field(description="业务用户 ID。")
    uid: str | None = Field(default=None, description="ERP UID。")
    authorization: str | None = Field(default=None, description="ERP Authorization。")


class LoadDailyReportContextInput(DailyReportToolUserInput):
    report_type: int = Field(default=1, description="日志类型，日报为 1。")
    report_date: str | None = Field(default=None, description="日志日期，格式 YYYY-MM-DD。")


class DailyReportPayloadInput(DailyReportToolUserInput):
    payload: dict[str, Any] = Field(description="日报提交或草稿 payload。")


@tool(args_schema=LoadDailyReportContextInput)
def load_daily_report_context(
    user_id: str,
    report_type: int = 1,
    report_date: str | None = None,
    uid: str | None = None,
    authorization: str | None = None,
) -> dict[str, Any]:
    """加载日报字段、配置、草稿和同步数据，并返回默认日报 payload。"""
    context = daily_report_service.load_context(
        _tool_user(user_id, uid, authorization),
        report_type=report_type,
        report_date=report_date,
    )
    return context.model_dump()


@tool(args_schema=DailyReportPayloadInput)
def save_daily_report_draft(
    user_id: str,
    payload: dict[str, Any],
    uid: str | None = None,
    authorization: str | None = None,
) -> dict[str, Any]:
    """保存日报草稿。"""
    return daily_report_service.save_draft_payload(
        _tool_user(user_id, uid, authorization),
        payload,
    )


@tool(args_schema=DailyReportPayloadInput)
def preview_daily_report_payload(
    user_id: str,
    payload: dict[str, Any],
    uid: str | None = None,
    authorization: str | None = None,
) -> dict[str, Any]:
    """生成日报提交前预览。"""
    return daily_report_service.preview_from_payload(payload)


@tool(args_schema=DailyReportPayloadInput)
def submit_daily_report_payload(
    user_id: str,
    payload: dict[str, Any],
    uid: str | None = None,
    authorization: str | None = None,
) -> dict[str, Any]:
    """提交日报。"""
    result = daily_report_service.submit_payload(
        _tool_user(user_id, uid, authorization),
        payload,
    )
    return result.model_dump()


DAILY_REPORT_TOOLS = [
    load_daily_report_context,
    save_daily_report_draft,
    preview_daily_report_payload,
    submit_daily_report_payload,
]


def _tool_user(
    user_id: str,
    uid: str | None = None,
    authorization: str | None = None,
) -> UserContext:
    # 日报接口主要依赖 uid/authorization；其它组织字段在这里用空值补齐，
    # 保持和现有 UserContext 类型兼容。
    return UserContext(
        user_id=user_id,
        name=f"User {user_id}",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid=uid,
        authorization=authorization,
    )

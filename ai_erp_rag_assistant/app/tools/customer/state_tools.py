"""基于已验证 State 查询 ERP 客户管理动态。"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import date, timedelta
from typing import Any

from ai_erp_rag_assistant.app.graph.state import CustomerState, ErpRagState
from ai_erp_rag_assistant.app.tools.erp.state_tools import get_current_user_from_state
from ai_erp_rag_assistant.app.tools.erp_tools import get_customer_activity


_ISO_DATE = re.compile(r"(?<!\d)(\d{4}-\d{2}-\d{2})(?!\d)")


def customer_activity_date_range(
    query: str,
    *,
    today: date | None = None,
) -> list[str]:
    """从常用中文日期表达式生成最多 31 天的闭区间。"""
    current = today or date.today()
    matches = [date.fromisoformat(value) for value in _ISO_DATE.findall(query)[:2]]
    if matches:
        start, end = (matches[0], matches[-1])
    elif "前天" in query:
        start = end = current - timedelta(days=2)
    elif "昨天" in query or "昨日" in query:
        start = end = current - timedelta(days=1)
    elif "本周" in query or "这周" in query:
        start, end = current - timedelta(days=current.weekday()), current
    elif "本月" in query or "这个月" in query:
        start, end = current.replace(day=1), current
    else:
        start = end = current
    if start > end:
        start, end = end, start
    if (end - start).days > 30:
        raise ValueError("客户动态单次查询最多支持 31 天")
    return [start.isoformat(), end.isoformat()]


def query_customer_activity_from_state(
    state: CustomerState | ErpRagState,
) -> dict[str, Any]:
    """只使用 ERP 已验证身份查询客户动态，不信任请求体租户字段。"""
    user = get_current_user_from_state(state)
    plan = state.get("plan")
    planned_query = str(plan.get("query") or "") if isinstance(plan, Mapping) else ""
    query = str(state.get("query") or planned_query or state.get("user_message") or "").strip()
    if not query:
        raise ValueError("客户管理 State 缺少查询内容")
    return get_customer_activity(
        query,
        customer_activity_date_range(query),
        user=user,
    )

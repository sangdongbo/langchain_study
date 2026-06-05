from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.tools import tool


def _request_id(prefix: str) -> str:
    return f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}"


def _approval_node(approval_type: str, slots: dict[str, str]) -> str:
    if approval_type == "expense":
        amount = _safe_number(slots.get("amount", "0"))
        return "部门负责人审批" if amount >= 5000 else "直属主管审批"
    if approval_type == "purchase":
        budget = _safe_number(slots.get("budget", "0"))
        return "采购主管审批" if budget >= 10000 else "直属主管审批"
    return "直属主管审批"


def _safe_number(value: str) -> float:
    digits = "".join(ch for ch in value if ch.isdigit() or ch == ".")
    if not digits:
        return 0.0
    return float(digits)


@tool("submit_leave_request")
def submit_leave_request(slots: dict[str, str], user_id: str = "U001") -> dict[str, Any]:
    """Submit a leave approval request after user confirmation."""

    return _submit("leave", "LR", slots, user_id)


@tool("submit_expense_request")
def submit_expense_request(slots: dict[str, str], user_id: str = "U001") -> dict[str, Any]:
    """Submit an expense approval request after user confirmation."""

    return _submit("expense", "EX", slots, user_id)


@tool("submit_purchase_request")
def submit_purchase_request(slots: dict[str, str], user_id: str = "U001") -> dict[str, Any]:
    """Submit a purchase approval request after user confirmation."""

    return _submit("purchase", "PR", slots, user_id)


@tool("get_leave_balance")
def get_leave_balance(user_id: str = "U001") -> dict[str, Any]:
    """Query mock leave balances for the current user."""

    return {
        "source": "mock",
        "data": {
            "user_id": user_id,
            "balances": {
                "年假": "5 天",
                "调休": "2 天",
                "病假": "按制度审批",
                "事假": "按制度审批",
            },
        },
    }


def _submit(approval_type: str, prefix: str, slots: dict[str, str], user_id: str) -> dict[str, Any]:
    approval_node = _approval_node(approval_type, slots)
    return {
        "source": "mock",
        "data": {
            "request_id": _request_id(prefix),
            "approval_type": approval_type,
            "user_id": user_id,
            "slots": dict(slots),
            "status": "待审批",
            "approval_node": approval_node,
        },
    }


TOOLS_BY_NAME = {
    "submit_leave_request": submit_leave_request,
    "submit_expense_request": submit_expense_request,
    "submit_purchase_request": submit_purchase_request,
    "get_leave_balance": get_leave_balance,
}


def run_submit_tool(name: str, slots: dict[str, str]) -> dict[str, Any]:
    return TOOLS_BY_NAME[name].invoke({"slots": slots})

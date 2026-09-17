from __future__ import annotations

import json
from hashlib import sha256

from langchain_core.tools import tool


INVENTORY = {
    "AI 推理服务器": 1,
    "开发笔记本": 12,
    "显示器": 30,
}

BUDGETS = {
    "研发平台部": 268_000.0,
    "产品部": 120_000.0,
    "行政部": 80_000.0,
}

SUPPLIERS = {
    "北辰智能硬件": {"risk": "medium", "score": 82, "late_deliveries": 1},
    "远景科技": {"risk": "low", "score": 94, "late_deliveries": 0},
    "未知供应商": {"risk": "high", "score": 40, "late_deliveries": 3},
}


def _json(data: dict) -> str:
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


@tool
def check_inventory(item: str, quantity: int) -> str:
    """Check mock inventory for an item and requested quantity."""
    available = INVENTORY.get(item, 0)
    return _json(
        {
            "item": item,
            "requested": quantity,
            "available": available,
            "enough": available >= quantity,
        }
    )


@tool
def check_budget(department: str, amount: float) -> str:
    """Check whether a department has enough mock procurement budget."""
    available = BUDGETS.get(department, 0.0)
    return _json(
        {
            "department": department,
            "requested_amount": amount,
            "available_budget": available,
            "enough": available >= amount,
            "gap": max(amount - available, 0.0),
        }
    )


@tool
def check_supplier(supplier: str) -> str:
    """Return mock supplier risk evidence."""
    data = SUPPLIERS.get(supplier, SUPPLIERS["未知供应商"])
    return _json({"supplier": supplier, **data})


@tool
def calculate_total(unit_price: float, quantity: int) -> str:
    """Calculate a procurement total using deterministic code."""
    return _json(
        {
            "unit_price": unit_price,
            "quantity": quantity,
            "total": round(unit_price * quantity, 2),
        }
    )


@tool
def publish_review(title: str, decision: str, summary: str) -> str:
    """Publish a mock final review. This tool is protected by human approval."""
    digest = sha256(f"{title}|{decision}|{summary}".encode()).hexdigest()[:12]
    return _json(
        {
            "status": "published",
            "review_id": f"review-{digest}",
            "title": title,
            "decision": decision,
        }
    )


PROCUREMENT_TOOLS = [
    calculate_total,
    check_inventory,
    check_budget,
    check_supplier,
]

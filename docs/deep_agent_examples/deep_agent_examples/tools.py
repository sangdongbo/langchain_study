"""采购评审示例使用的确定性工具。

数据全部来自本文件中的固定字典，不访问真实库存、预算或供应商系统。
模型负责决定何时调用工具，工具只负责返回可复现、可验证的 JSON 证据。
"""

from __future__ import annotations

import json
from hashlib import sha256

from langchain_core.tools import tool


# 模拟库存：key 为物品名称，value 为当前可用数量。
INVENTORY = {
    "AI 推理服务器": 1,
    "开发笔记本": 12,
    "显示器": 30,
}

# 模拟部门预算，金额单位由示例统一按“元”理解。
BUDGETS = {
    "研发平台部": 268_000.0,
    "产品部": 120_000.0,
    "行政部": 80_000.0,
}

# 模拟供应商画像；找不到供应商时统一使用“未知供应商”的高风险数据。
SUPPLIERS = {
    "北辰智能硬件": {"risk": "medium", "score": 82, "late_deliveries": 1},
    "远景科技": {"risk": "low", "score": 94, "late_deliveries": 0},
    "未知供应商": {"risk": "high", "score": 40, "late_deliveries": 3},
}


def _json(data: dict) -> str:
    """把工具结果稳定序列化为中文可读的 JSON 字符串。"""
    return json.dumps(data, ensure_ascii=False, sort_keys=True)


@tool
def check_inventory(item: str, quantity: int) -> str:
    """检查模拟库存是否满足申请数量，并返回申请量、库存量和是否充足。"""
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
    """检查部门模拟预算，并返回可用预算、是否充足和不足金额。"""
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
    """查询模拟供应商风险；未知名称按高风险供应商处理。"""
    data = SUPPLIERS.get(supplier, SUPPLIERS["未知供应商"])
    return _json({"supplier": supplier, **data})


@tool
def calculate_total(unit_price: float, quantity: int) -> str:
    """用确定性代码计算采购总额，避免模型自行心算产生误差。"""
    return _json(
        {
            "unit_price": unit_price,
            "quantity": quantity,
            "total": round(unit_price * quantity, 2),
        }
    )


@tool
def publish_review(title: str, decision: str, summary: str) -> str:
    """模拟发布最终评审。

    图配置会要求该工具在人工批准后才能执行；哈希摘要生成稳定的模拟评审 ID，
    不会调用任何真实发布接口。
    """
    digest = sha256(f"{title}|{decision}|{summary}".encode()).hexdigest()[:12]
    return _json(
        {
            "status": "published",
            "review_id": f"review-{digest}",
            "title": title,
            "decision": decision,
        }
    )


# 默认采购 Agent 可直接使用的只读证据工具集合；发布工具需单独显式加入。
PROCUREMENT_TOOLS = [
    calculate_total,
    check_inventory,
    check_budget,
    check_supplier,
]

from __future__ import annotations

import json
import re

from approval_graph_demo.model import build_deepseek_model


LEAVE_TYPES = ("年假", "事假", "病假", "调休")
EXPENSE_TYPES = ("差旅费", "餐饮费", "办公用品", "交通费", "住宿费")
LEAVE_BALANCE_WORDS = ("假期", "年假", "调休", "病假", "事假")
QUERY_WORDS = ("查", "查询", "余额", "剩", "还有多少", "多少天", "剩余")


def classify_approval_type(text: str, allow_model: bool = True) -> str | None:
    """Classify approval type with deterministic rules first."""

    if any(word in text for word in ("请假", "休假", "病假", "年假", "调休", "事假")):
        return "leave"
    if any(word in text for word in ("报销", "发票", "差旅费", "餐饮费", "交通费", "住宿费")):
        return "expense"
    if any(word in text for word in ("采购", "购买", "申请购买", "购置")):
        return "purchase"
    if "买" in text and any(word in text for word in ("审批", "申请", "办公", "设备", "电脑", "物品")):
        return "purchase"
    if not allow_model:
        return None
    return _classify_with_model(text)


def is_leave_balance_query(text: str) -> bool:
    """Return True when the user is asking about remaining leave days."""

    return any(word in text for word in LEAVE_BALANCE_WORDS) and any(word in text for word in QUERY_WORDS)


def extract_slots(approval_type: str, text: str) -> dict[str, str]:
    """Extract slots for one approval type."""

    if approval_type == "leave":
        slots = _extract_leave(text)
    elif approval_type == "expense":
        slots = _extract_expense(text)
    elif approval_type == "purchase":
        slots = _extract_purchase(text)
    else:
        slots = {}

    if slots:
        return slots
    return _extract_with_model(approval_type, text)


def extract_modifications(text: str) -> dict[str, str]:
    """Extract field modifications from a confirmation-stage message."""

    slots: dict[str, str] = {}
    amount = _find_number_after(text, ("金额",))
    if amount:
        slots["amount"] = amount
    if "预算" in text:
        budget = _find_number_after(text, ("预算",))
        if budget:
            slots["budget"] = budget
    dates = _dates(text)
    if "开始" in text and dates:
        slots["start_date"] = dates[0]
    if "结束" in text and dates:
        slots["end_date"] = dates[0]
    if "原因" in text or "事由" in text or "用途" in text:
        reason = re.sub(r"^(修改|改|把)?(原因|事由|用途)(为|改为|是)?", "", text).strip()
        if reason:
            slots["reason"] = reason
            slots["purpose"] = reason
    return {k: v for k, v in slots.items() if v}


def _extract_leave(text: str) -> dict[str, str]:
    slots: dict[str, str] = {}
    for leave_type in LEAVE_TYPES:
        if leave_type in text:
            slots["leave_type"] = leave_type
            break
    dates = _dates(text)
    if dates:
        slots["start_date"] = dates[0]
    if len(dates) >= 2:
        slots["end_date"] = dates[1]
    reason = _after_marker(text, ("因为", "原因是", "理由是"))
    if reason:
        slots["reason"] = reason
    return slots


def _extract_expense(text: str) -> dict[str, str]:
    slots: dict[str, str] = {}
    for expense_type in EXPENSE_TYPES:
        if expense_type in text:
            slots["expense_type"] = expense_type
            break
    amount = _find_number_after(text, ("金额", "报销"))
    if amount:
        slots["amount"] = amount
    reason = _after_marker(text, ("事由是", "因为", "用于", "原因是"))
    if reason:
        slots["reason"] = reason
    if "发票" in text:
        slots["invoice"] = "已提供" if any(word in text for word in ("已", "有", "提供")) else "待补充"
    return slots


def _extract_purchase(text: str) -> dict[str, str]:
    slots: dict[str, str] = {}
    item_match = re.search(r"(?:采购|购买|买|购置)(?P<item>[\u4e00-\u9fa5A-Za-z0-9]+)", text)
    if item_match:
        slots["item"] = item_match.group("item").strip("，。,. ")
    quantity = _find_number_after(text, ("数量", "采购", "购买", "买"))
    if quantity:
        slots["quantity"] = quantity
    if "预算" in text:
        budget = _find_number_after(text, ("预算",))
        if budget:
            slots["budget"] = budget
    purpose = _after_marker(text, ("用途是", "用于", "为了"))
    if purpose:
        slots["purpose"] = purpose
    return slots


def _dates(text: str) -> list[str]:
    matches = re.findall(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?", text)
    normalized = []
    for value in matches:
        parts = re.findall(r"\d+", value)
        if len(parts) >= 3:
            normalized.append(f"{int(parts[0]):04d}-{int(parts[1]):02d}-{int(parts[2]):02d}")
    return normalized


def _find_number_after(text: str, markers: tuple[str, ...]) -> str | None:
    for marker in markers:
        pattern = rf"{marker}[^0-9]*(\d+(?:\.\d+)?)"
        match = re.search(pattern, text)
        if match:
            return match.group(1)
    match = re.search(r"(\d+(?:\.\d+)?)", text)
    return match.group(1) if match else None


def _after_marker(text: str, markers: tuple[str, ...]) -> str | None:
    for marker in markers:
        if marker in text:
            return text.split(marker, 1)[1].strip(" ，。,.;；")
    return None


def _classify_with_model(text: str) -> str | None:
    model = build_deepseek_model()
    if model is None:
        return None
    prompt = (
        "判断用户要办理的审批类型，只返回 leave、expense、purchase 或 unknown。"
        f"\n用户输入：{text}"
    )
    try:
        content = model.invoke(prompt).content.strip().lower()
    except Exception:
        return None
    if "leave" in content:
        return "leave"
    if "expense" in content:
        return "expense"
    if "purchase" in content:
        return "purchase"
    return None


def _extract_with_model(approval_type: str, text: str) -> dict[str, str]:
    model = build_deepseek_model()
    if model is None:
        return {}
    prompt = (
        "从用户输入中抽取审批字段，返回 JSON 对象，不要解释。"
        f"\n审批类型：{approval_type}\n用户输入：{text}"
    )
    try:
        content = model.invoke(prompt).content
        data = json.loads(content)
    except Exception:
        return {}
    return {str(k): str(v) for k, v in data.items() if v is not None}

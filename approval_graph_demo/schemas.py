from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ApprovalDefinition:
    """Configuration for one approval workflow."""

    approval_type: str
    title: str
    fields: tuple[str, ...]
    field_labels: dict[str, str]
    submit_tool: str
    request_prefix: str


APPROVAL_DEFINITIONS: dict[str, ApprovalDefinition] = {
    "leave": ApprovalDefinition(
        approval_type="leave",
        title="请假申请",
        fields=("leave_type", "start_date", "end_date", "reason"),
        field_labels={
            "leave_type": "请假类型",
            "start_date": "开始时间",
            "end_date": "结束时间",
            "reason": "请假原因",
        },
        submit_tool="submit_leave_request",
        request_prefix="LR",
    ),
    "expense": ApprovalDefinition(
        approval_type="expense",
        title="报销申请",
        fields=("expense_type", "amount", "reason", "invoice"),
        field_labels={
            "expense_type": "报销类型",
            "amount": "金额",
            "reason": "报销事由",
            "invoice": "发票情况",
        },
        submit_tool="submit_expense_request",
        request_prefix="EX",
    ),
    "purchase": ApprovalDefinition(
        approval_type="purchase",
        title="采购申请",
        fields=("item", "quantity", "budget", "purpose"),
        field_labels={
            "item": "采购物品",
            "quantity": "数量",
            "budget": "预算",
            "purpose": "采购用途",
        },
        submit_tool="submit_purchase_request",
        request_prefix="PR",
    ),
}


QUESTIONS: dict[str, str] = {
    "leave_type": "请先选择请假类型：年假、事假、病假、调休。",
    "start_date": "请告诉我请假的开始时间，例如 2026-06-01。",
    "end_date": "请告诉我请假的结束时间，例如 2026-06-03。",
    "reason": "请补充申请原因。",
    "expense_type": "请告诉我报销类型，例如差旅费、餐饮费、办公用品。",
    "amount": "请告诉我报销金额，例如 3200。",
    "invoice": "请说明发票情况，例如已提供、待补充、无发票。",
    "item": "请告诉我采购物品名称。",
    "quantity": "请告诉我采购数量。",
    "budget": "请告诉我采购预算，例如 12000。",
    "purpose": "请说明采购用途。",
}


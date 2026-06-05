from __future__ import annotations

from datetime import date
from typing import Literal

from langgraph.graph import END, START, StateGraph

from approval_graph_demo.extractors import (
    classify_approval_type,
    extract_modifications,
    extract_slots,
    is_leave_balance_query,
)
from approval_graph_demo.schemas import APPROVAL_DEFINITIONS, QUESTIONS
from approval_graph_demo.state import ApprovalState
from approval_graph_demo.tools import get_leave_balance, run_submit_tool


CONFIRM_WORDS = ("确认", "确认提交", "提交", "没问题", "可以提交")
CANCEL_WORDS = (
    "取消",
    "不提交",
    "算了",
    "不想",
    "不要",
    "不办",
    "停止",
    "结束",
    "先不",
    "不用了",
)


def create_approval_graph():
    """Create the approval workflow graph."""

    builder = StateGraph(ApprovalState)
    builder.add_node("classify", classify_node)
    builder.add_node("collect", collect_node)
    builder.add_node("validate", validate_node)
    builder.add_node("preview", preview_node)
    builder.add_node("submit", submit_node)
    builder.add_node("cancel", cancel_node)
    builder.add_node("balance", balance_node)
    builder.add_node("clarify", clarify_node)

    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        route_after_classify,
        {
            "collect": "collect",
            "submit": "submit",
            "cancel": "cancel",
            "balance": "balance",
            "clarify": "clarify",
        },
    )
    builder.add_conditional_edges(
        "collect",
        route_after_collect,
        {
            "wait": END,
            "validate": "validate",
        },
    )
    builder.add_conditional_edges(
        "validate",
        route_after_validate,
        {
            "wait": END,
            "preview": "preview",
        },
    )
    builder.add_edge("preview", END)
    builder.add_edge("submit", END)
    builder.add_edge("cancel", END)
    builder.add_edge("balance", END)
    builder.add_edge("clarify", END)

    return builder.compile()


def classify_node(state: ApprovalState) -> ApprovalState:
    """Determine whether this is a new flow, confirmation, cancellation, or update."""

    text = state.get("user_message", "").strip()
    current_status = state.get("status", "idle")

    if current_status in {"collecting", "awaiting_confirmation"} and _is_cancel(text):
        return {**state, "route": "cancel"}

    if is_leave_balance_query(text):
        return {**state, "route": "balance"}

    detected_type = classify_approval_type(text, allow_model=current_status == "idle")

    if current_status == "awaiting_confirmation":
        if _is_confirm(text):
            return {**state, "route": "submit", "confirmed": True}
        modifications = extract_modifications(text)
        if modifications:
            slots = {**state.get("slots", {}), **_filter_slots(state.get("approval_type"), modifications)}
            return {
                **state,
                "slots": slots,
                "status": "collecting",
                "confirmed": False,
                "request_id": None,
                "route": "collect",
            }
        return {
            **state,
            "route": "clarify",
            "assistant_message": "请回复“确认提交”、说明要修改的字段，或回复“取消”。",
        }

    if current_status == "collecting" and state.get("approval_type"):
        if detected_type and detected_type != state.get("approval_type") and _is_switch_intent(text):
            return {
                **state,
                "approval_type": detected_type,
                "status": "collecting",
                "route": "collect",
                "slots": extract_slots(detected_type, text),
                "awaiting": None,
                "request_id": None,
                "approval_node": None,
                "tool_result": None,
                "confirmed": False,
            }
        return {
            **state,
            "route": "collect",
            "confirmed": False,
            "request_id": None,
        }

    approval_type = detected_type
    if approval_type is None:
        return {
            **state,
            "approval_type": None,
            "route": "clarify",
            "assistant_message": "请告诉我要办理哪类审批：请假、报销或采购。",
        }

    return {
        **state,
        "approval_type": approval_type,
        "status": "collecting",
        "route": "collect",
        "slots": _filter_slots(approval_type, {**state.get("slots", {}), **extract_slots(approval_type, text)}),
        "request_id": None,
        "approval_node": None,
        "tool_result": None,
        "confirmed": False,
    }


def collect_node(state: ApprovalState) -> ApprovalState:
    """Ask for the next missing field, or continue to validation."""

    approval_type = state.get("approval_type")
    if not approval_type:
        return {**state, "route": "clarify"}

    slots = dict(state.get("slots", {}))
    awaiting = state.get("awaiting")
    text = state.get("user_message", "").strip()

    extracted_slots = _filter_slots(approval_type, extract_slots(approval_type, text))
    if _mentions_other_approval_type(approval_type, text):
        extracted_slots = {key: value for key, value in extracted_slots.items() if key == awaiting}
    if awaiting in {"leave_type", "expense_type"} and awaiting not in extracted_slots:
        extracted_slots = {}
    slots.update(extracted_slots)
    if awaiting and text and awaiting not in slots:
        raw_value = _raw_value_for_awaiting(approval_type, awaiting, text)
        if raw_value:
            slots[awaiting] = raw_value
    missing = _first_missing_field(approval_type, slots)

    if missing:
        return {
            **state,
            "slots": slots,
            "awaiting": missing,
            "status": "collecting",
            "route": "wait",
            "assistant_message": QUESTIONS[missing],
        }

    return {
        **state,
        "slots": slots,
        "awaiting": None,
        "status": "collecting",
        "route": "validate",
    }


def validate_node(state: ApprovalState) -> ApprovalState:
    """Validate collected fields before preview."""

    approval_type = state.get("approval_type")
    slots = state.get("slots", {})
    errors: list[str] = []

    if approval_type == "leave":
        start_date = slots.get("start_date", "")
        end_date = slots.get("end_date", "")
        if start_date and end_date and start_date > end_date:
            errors.append("开始时间不能晚于结束时间，请重新提供请假时间。")
    if approval_type == "expense":
        if _number(slots.get("amount", "0")) <= 0:
            errors.append("报销金额必须大于 0，请重新提供金额。")
    if approval_type == "purchase":
        if _number(slots.get("quantity", "0")) <= 0:
            errors.append("采购数量必须大于 0，请重新提供数量。")
        if _number(slots.get("budget", "0")) <= 0:
            errors.append("采购预算必须大于 0，请重新提供预算。")

    if errors:
        return {
            **state,
            "errors": errors,
            "status": "collecting",
            "awaiting": _first_missing_field(approval_type, slots),
            "route": "wait",
            "assistant_message": "\n".join(errors),
        }

    return {**state, "errors": [], "route": "preview"}


def preview_node(state: ApprovalState) -> ApprovalState:
    """Build a human-readable preview and wait for explicit confirmation."""

    approval_type = state["approval_type"]
    definition = APPROVAL_DEFINITIONS[approval_type]
    slots = state.get("slots", {})
    approval_node = _approval_node(approval_type, slots)

    lines = [f"请确认是否提交{definition.title}：", ""]
    for field in definition.fields:
        label = definition.field_labels[field]
        lines.append(f"- {label}：{slots.get(field, '')}")
    lines.extend(
        [
            f"- 预计审批节点：{approval_node}",
            "",
            "回复“确认提交”后我再提交申请。",
            "也可以回复“修改金额为 3000”这类指令继续修改，或回复“取消”。",
        ]
    )
    preview = "\n".join(lines)
    return {
        **state,
        "preview": preview,
        "assistant_message": preview,
        "approval_node": approval_node,
        "status": "awaiting_confirmation",
        "confirmed": False,
        "route": "preview",
    }


def submit_node(state: ApprovalState) -> ApprovalState:
    """Submit only after explicit user confirmation."""

    approval_type = state["approval_type"]
    definition = APPROVAL_DEFINITIONS[approval_type]
    tool_result = run_submit_tool(definition.submit_tool, state.get("slots", {}))
    data = tool_result["data"]
    request_id = data["request_id"]
    approval_node = data["approval_node"]
    return {
        **state,
        "status": "submitted",
        "confirmed": True,
        "request_id": request_id,
        "approval_node": approval_node,
        "tool_result": tool_result,
        "assistant_message": (
            f"已提交{definition.title}。\n\n"
            f"- 申请编号：{request_id}\n"
            f"- 当前状态：待审批\n"
            f"- 审批节点：{approval_node}"
        ),
        "route": "submit",
    }


def cancel_node(state: ApprovalState) -> ApprovalState:
    """Cancel the current approval flow."""

    return {
        **state,
        "status": "cancelled",
        "approval_type": None,
        "awaiting": None,
        "slots": {},
        "preview": "",
        "assistant_message": "已取消本次审批申请，没有提交任何内容。",
        "confirmed": False,
        "request_id": None,
        "approval_node": None,
        "tool_result": None,
        "route": "cancel",
    }


def balance_node(state: ApprovalState) -> ApprovalState:
    """Answer leave-balance queries without starting an approval flow."""

    tool_result = get_leave_balance.invoke({"user_id": "U001"})
    balances = tool_result["data"]["balances"]
    lines = ["已为你查询到假期余额："]
    lines.extend(f"- {name}：{value}" for name, value in balances.items())
    lines.append("")
    lines.append("如果要发起请假申请，可以直接说“我要请年假，从哪天到哪天，原因是什么”。")
    return {
        **state,
        "approval_type": None,
        "status": "idle",
        "awaiting": None,
        "slots": {},
        "assistant_message": "\n".join(lines),
        "preview": "",
        "confirmed": False,
        "request_id": None,
        "approval_node": None,
        "tool_result": tool_result,
        "route": "balance",
    }


def clarify_node(state: ApprovalState) -> ApprovalState:
    """Return a clarification message."""

    message = state.get("assistant_message") or "请告诉我要办理哪类审批：请假、报销或采购。"
    return {**state, "assistant_message": message, "route": "clarify"}


def route_after_classify(state: ApprovalState) -> Literal["collect", "submit", "cancel", "balance", "clarify"]:
    return state.get("route", "clarify")  # type: ignore[return-value]


def route_after_collect(state: ApprovalState) -> Literal["wait", "validate"]:
    return state.get("route", "wait")  # type: ignore[return-value]


def route_after_validate(state: ApprovalState) -> Literal["wait", "preview"]:
    return state.get("route", "preview")  # type: ignore[return-value]


def _first_missing_field(approval_type: str | None, slots: dict[str, str]) -> str | None:
    if not approval_type:
        return None
    for field in APPROVAL_DEFINITIONS[approval_type].fields:
        if not slots.get(field):
            return field
    return None


def _filter_slots(approval_type: str | None, slots: dict[str, str]) -> dict[str, str]:
    if not approval_type:
        return {}
    allowed = set(APPROVAL_DEFINITIONS[approval_type].fields)
    return {key: value for key, value in slots.items() if key in allowed and value}


def _normalize_field_value(field: str, value: str) -> str:
    text = value.strip()
    if field in {"amount", "budget", "quantity"}:
        digits = "".join(ch for ch in text if ch.isdigit() or ch == ".")
        return digits or text
    return text


def _raw_value_for_awaiting(approval_type: str, field: str, value: str) -> str | None:
    if _mentions_other_approval_type(approval_type, value):
        return None
    if field == "leave_type":
        allowed = {"年假", "事假", "病假", "调休"}
        return value.strip() if value.strip() in allowed else None
    if field == "expense_type":
        allowed = {"差旅费", "餐饮费", "办公用品", "交通费", "住宿费"}
        return value.strip() if value.strip() in allowed else None
    if approval_type == "expense" and field == "amount":
        if any(word in value for word in ("采购", "购买", "请假", "休假")):
            return None
    return _normalize_field_value(field, value)


def _number(value: str) -> float:
    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch == ".")
    if not digits:
        return 0.0
    return float(digits)


def _approval_node(approval_type: str, slots: dict[str, str]) -> str:
    if approval_type == "expense" and _number(slots.get("amount", "0")) >= 5000:
        return "部门负责人审批"
    if approval_type == "purchase" and _number(slots.get("budget", "0")) >= 10000:
        return "采购主管审批"
    return "直属主管审批"


def _is_confirm(text: str) -> bool:
    return any(word in text for word in CONFIRM_WORDS)


def _is_cancel(text: str) -> bool:
    return any(word in text for word in CANCEL_WORDS)


def _is_switch_intent(text: str) -> bool:
    return any(word in text for word in ("改成", "换成", "改为", "换为", "重新申请", "重新办理", "不要这个"))


def _mentions_other_approval_type(approval_type: str, text: str) -> bool:
    type_words = {
        "leave": ("请假", "休假", "病假", "年假", "调休", "事假"),
        "expense": ("报销", "发票", "差旅费", "餐饮费", "交通费", "住宿费"),
        "purchase": ("采购", "购买", "申请购买", "购置"),
    }
    for other_type, words in type_words.items():
        if other_type != approval_type and any(word in text for word in words):
            return True
    return False

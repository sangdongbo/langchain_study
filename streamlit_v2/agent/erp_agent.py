from __future__ import annotations

import re
from dataclasses import dataclass, field

from streamlit_v2.tools.registry import run_tool


# Agent 层只负责判断意图、维护多轮状态、决定调用哪个 LangChain tool。
# 具体工具定义在 streamlit_v2/tools，下方文案只面向最终用户。
LEAVE_TYPES = ("年假", "事假", "病假", "调休")
LEAVE_FIELD_ORDER = ("leave_type", "start_date", "end_date", "reason")


@dataclass
class ERPFlowState:
    """保存一个会话里的 ERP 多轮流程状态。

    intent 表示当前流程，例如 leave_request；awaiting 表示下一轮等待的字段；
    slots 是已收集到的工具参数。
    """

    intent: str | None = None
    awaiting: str | None = None
    slots: dict[str, str] = field(default_factory=dict)


@dataclass
class ERPAgentResponse:
    """ERP Agent 返回给页面层的结果。"""

    handled: bool
    message: str


def handle_erp_message(
    message: str,
    state: ERPFlowState | None = None,
) -> tuple[ERPAgentResponse, ERPFlowState]:
    """处理一轮用户输入。

    handled=False 代表不是当前规则能处理的 ERP 消息，页面可以继续交给 LLM；
    handled=True 代表已经完成追问、工具调用或业务回复。
    """

    current_state = state or ERPFlowState()
    text = message.strip()

    if current_state.intent == "leave_request":
        return _continue_leave_request(text, current_state)

    if _is_leave_balance_query(text):
        return _answer_leave_balance(), ERPFlowState()

    if _is_leave_request(text):
        slots = _extract_leave_slots(text)
        return _next_leave_step(slots)

    if _is_standalone_leave_type(text):
        return _next_leave_step({"leave_type": _normalize_slot_value("leave_type", text)})

    return ERPAgentResponse(handled=False, message=""), current_state


def _continue_leave_request(text: str, state: ERPFlowState) -> tuple[ERPAgentResponse, ERPFlowState]:
    # 多轮流程中，用户本轮回答优先填入 awaiting 对应字段；
    # 同时再从整句话里抽取其它可能顺手提供的字段。
    slots = dict(state.slots)
    if state.awaiting:
        slots[state.awaiting] = _normalize_slot_value(state.awaiting, text)
    for field_name, value in _extract_leave_slots(text).items():
        slots.setdefault(field_name, value)
    return _next_leave_step(slots)


def _next_leave_step(slots: dict[str, str]) -> tuple[ERPAgentResponse, ERPFlowState]:
    # 缺字段时继续追问，字段完整时调用 LangChain tool。
    missing_field = _first_missing_leave_field(slots)
    if missing_field:
        next_state = ERPFlowState(
            intent="leave_request",
            awaiting=missing_field,
            slots=slots,
        )
        return ERPAgentResponse(handled=True, message=_question_for_field(missing_field)), next_state

    tool_result = run_tool("create_leave_request", slots)
    request = tool_result["data"]
    message = (
        "已为你创建请假申请。\n\n"
        f"- 申请编号：{request['request_id']}\n"
        f"- 请假类型：{request['leave_type']}\n"
        f"- 时间：{request['start_date']} 至 {request['end_date']}\n"
        f"- 原因：{request['reason']}\n"
        f"- 当前状态：{request['status']}\n"
        f"- 审批节点：{request['approval_node']}"
    )
    return ERPAgentResponse(handled=True, message=message), ERPFlowState()


def _answer_leave_balance() -> ERPAgentResponse:
    tool_result = run_tool("get_leave_balance", {"user_id": "U001"})
    balance = tool_result["data"]["balances"]
    message = (
        "已为你查询到假期余额：\n\n"
        f"- 年假：{balance['年假']} 天\n"
        f"- 事假：{balance['事假']} 天\n"
        f"- 病假：{balance['病假']} 天\n"
        f"- 调休：{balance['调休']} 天"
    )
    return ERPAgentResponse(handled=True, message=message)


def _is_leave_request(text: str) -> bool:
    request_keywords = ("请假", "休假", "申请假", "请个假")
    balance_keywords = ("剩", "余额", "还有多少", "多少天", "几天", "还剩")
    if any(keyword in text for keyword in balance_keywords):
        return False
    if any(keyword in text for keyword in request_keywords):
        return True
    # 用户常说“申请病假/申请年假”，这类句子没有“请假”二字，
    # 但已经包含申请动作和具体假种，也应该进入多轮请假流程。
    return "申请" in text and any(leave_type in text for leave_type in LEAVE_TYPES)


def _is_leave_balance_query(text: str) -> bool:
    leave_keywords = ("年假", "假期", "调休", "病假", "事假")
    balance_keywords = ("剩", "余额", "还有多少", "多少天", "几天", "还剩")
    if not any(keyword in text for keyword in leave_keywords):
        return False
    if any(keyword in text for keyword in balance_keywords):
        return True
    return any(leave_type in text for leave_type in LEAVE_TYPES) and any(
        marker in text for marker in ("呢", "吗", "？", "?")
    )


def _is_standalone_leave_type(text: str) -> bool:
    return any(leave_type == text.strip() for leave_type in LEAVE_TYPES)


def _extract_leave_slots(text: str) -> dict[str, str]:
    slots: dict[str, str] = {}
    for leave_type in LEAVE_TYPES:
        if leave_type in text:
            slots["leave_type"] = leave_type
            break

    dates = re.findall(r"\d{4}[-/.年]\d{1,2}[-/.月]\d{1,2}日?", text)
    normalized_dates = [_normalize_date(date) for date in dates]
    if normalized_dates:
        slots["start_date"] = normalized_dates[0]
    if len(normalized_dates) >= 2:
        slots["end_date"] = normalized_dates[1]

    reason_match = re.search(r"(?:因为|原因是|理由是)(.+)$", text)
    if reason_match:
        slots["reason"] = reason_match.group(1).strip(" ，。,.;；")

    return slots


def _first_missing_leave_field(slots: dict[str, str]) -> str | None:
    for field_name in LEAVE_FIELD_ORDER:
        if not slots.get(field_name):
            return field_name
    return None


def _question_for_field(field_name: str) -> str:
    if field_name == "leave_type":
        return "好的，我来帮你创建请假申请。请先选择请假类型：年假、事假、病假、调休。"
    if field_name == "start_date":
        return "请告诉我请假的开始时间，例如 2026-06-01。"
    if field_name == "end_date":
        return "请告诉我请假的结束时间，例如 2026-06-03。"
    return "请补充请假原因。"


def _normalize_slot_value(field_name: str, value: str) -> str:
    text = value.strip()
    if field_name == "leave_type":
        for leave_type in LEAVE_TYPES:
            if leave_type in text:
                return leave_type
    if field_name in {"start_date", "end_date"}:
        return _normalize_date(text)
    return text


def _normalize_date(value: str) -> str:
    digits = re.findall(r"\d+", value)
    if len(digits) >= 3:
        year, month, day = digits[:3]
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return value.strip()

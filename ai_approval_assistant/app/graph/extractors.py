from __future__ import annotations
import re
from app.schemas.approval import ApprovalField, ApprovalTemplate

CONFIRM_WORDS = ("确认提交", "提交申请", "确认", "可以提交")
CANCEL_WORDS = ("取消", "不提交", "算了", "不办", "先不", "停止")
SWITCH_WORDS = ("改成", "换成", "改为", "换为", "重新申请", "重新办理")
APPROVAL_INTENT_WORDS = (
    "审批",
    "申请",
    "流程",
    "发起",
    "办理",
    "提交",
    "报销",
    "请假",
    "采购",
    "用章",
    "盖章",
    "入库",
    "出库",
    "外出",
    "出差",
    "加班",
)


def is_confirm_message(text: str) -> bool:
    """判断消息是否明确确认提交。"""
    return any((word in text for word in CONFIRM_WORDS))


def is_cancel_message(text: str) -> bool:
    """判断消息是否取消当前审批流程。"""
    return any((word in text for word in CANCEL_WORDS))


def is_switch_message(text: str) -> bool:
    """判断消息是否请求切换审批类型。"""
    return any((word in text for word in SWITCH_WORDS))


def has_approval_intent(text: str, templates: list[ApprovalTemplate]) -> bool:
    """判断消息是否像是在发起审批。"""
    if any((word in text for word in APPROVAL_INTENT_WORDS)):
        return True
    for template in templates:
        markers = {
            template.title,
            template.category,
            template.group_name or "",
            *template.aliases,
            *template.intent_keywords,
        }
        if any((marker and marker in text for marker in markers)):
            return True
    return False


def classify_approval_type(text: str, templates: list[ApprovalTemplate]) -> str | None:
    """根据消息文本和模板信息匹配审批类型。"""
    scored: list[tuple[int, str]] = []
    for template in templates:
        score = sum(
            (1 for keyword in template.intent_keywords if keyword and keyword in text)
        )
        score += sum(
            (
                1
                for field in template.fields
                for option in field.options
                if option and option in text
            )
        )
        if score > 0:
            scored.append((score, template.approval_type))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][1]


def extract_slots(
    template: ApprovalTemplate, text: str, awaiting_field: str | None = None
) -> dict[str, str]:
    """使用模板规则和上下文从文本中抽取字段值。"""
    slots: dict[str, str] = {}
    all_dates = _extract_dates(text)
    date_cursor = 0
    for field in template.fields:
        value = _extract_field_value(field, text)
        if not value and field.type == "date" and (date_cursor < len(all_dates)):
            value = all_dates[date_cursor]
            date_cursor += 1
        if not value and awaiting_field == field.name:
            value = _raw_value_for_awaiting(field, text)
        if value:
            slots[field.name] = value
    return slots


def _extract_field_value(field: ApprovalField, text: str) -> str | None:
    """从完整用户消息中抽取单个字段值。"""
    for pattern in field.extract_patterns:
        match = re.search(pattern, text)
        if match:
            value = next((group for group in match.groups() if group), match.group(0))
            return _normalize_value(field, value)
    if field.type == "enum":
        for option in field.options:
            if option in text:
                return option
    if field.type == "number" and _field_mentioned(field, text):
        return _extract_first_number(text)
    if field.type == "date" and _field_mentioned(field, text):
        dates = _extract_dates(text)
        return dates[0] if dates else None
    return None


def _raw_value_for_awaiting(field: ApprovalField, text: str) -> str | None:
    """将整条消息视为当前等待字段的回答。"""
    cleaned = text.strip(" ，。,.;；")
    if not cleaned:
        return None
    if field.type == "enum":
        for option in field.options:
            if option in cleaned:
                return option
        if not field.options:
            return cleaned
        return None
    if field.type == "number":
        return _extract_first_number(cleaned)
    if field.type == "date":
        dates = _extract_dates(cleaned)
        return dates[0] if dates else cleaned
    return cleaned


def _field_mentioned(field: ApprovalField, text: str) -> bool:
    """判断文本中是否出现字段标签或别名。"""
    markers = [field.label, *field.aliases]
    return any((marker and marker in text for marker in markers))


def _normalize_value(field: ApprovalField, value: str) -> str:
    """按目标字段类型规范化抽取结果。"""
    text = value.strip(" ，。,.;；")
    if field.type == "number":
        number = _extract_first_number(text)
        return number or text
    if field.type == "date":
        dates = _extract_dates(text)
        return dates[0] if dates else text
    if field.name == "invoice":
        if any((word in text for word in ("已提供", "提供了", "有"))):
            return "已提供"
        if any((word in text for word in ("待补充", "后补"))):
            return "待补充"
        if any((word in text for word in ("无", "没有"))):
            return "无发票"
    if field.name == "item":
        return re.sub("^\\d+[台个件套]?", "", text)
    return text


def _extract_dates(text: str) -> list[str]:
    """从用户文本中抽取类似日期的值。"""
    dates = re.findall("\\d{4}[-/.年]\\d{1,2}[-/.月]\\d{1,2}日?", text)
    return [_normalize_date(date) for date in dates]


def _normalize_date(value: str) -> str:
    """尽可能将类似日期的值规范化为 YYYY-MM-DD。"""
    digits = re.findall("\\d+", value)
    if len(digits) >= 3:
        year, month, day = digits[:3]
        return f"{int(year):04d}-{int(month):02d}-{int(day):02d}"
    return value


def _extract_first_number(text: str) -> str | None:
    """从文本中抽取第一个整数或小数。"""
    match = re.search("\\d+(?:\\.\\d+)?", text)
    return match.group(0) if match else None

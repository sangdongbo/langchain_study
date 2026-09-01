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
        return _extract_enum_option(field, text)
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
        if not field.options and not field.option_values:
            return cleaned
        return _extract_enum_option(field, cleaned)
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


def _extract_enum_option(field: ApprovalField, text: str) -> str | None:
    """从枚举字段中识别用户输入的选项。

    ERP 的动态选项经常把余额或时长拼到展示名称中，例如“年假（10天）”。
    用户通常只会说“年假”，因此除了完整标签外，还尝试匹配括号前的核心名称。
    只有核心名称唯一时才自动选择，避免多个同名假期被误选。
    """
    option_values = field.option_values or [
        {"label": option, "value": option} for option in field.options
    ]
    if not option_values:
        return None

    text = text.strip()
    exact_matches = [
        item
        for item in option_values
        if str(item.get("label") or "").strip()
        and str(item.get("label") or "").strip() in text
    ]
    if exact_matches:
        # 当一个选项是另一个选项的前缀时，优先选择更长的完整标签。
        exact_matches.sort(
            key=lambda item: len(str(item.get("label") or "")), reverse=True
        )
        return str(exact_matches[0]["label"]).strip()

    core_matches: list[tuple[str, dict[str, object]]] = []
    for item in option_values:
        label = str(item.get("label") or "").strip()
        core = _enum_option_core(label)
        if not core:
            continue
        candidates = [core]
        # “调休” is a common shorthand for an option labelled “调休假”。
        if core.endswith("假") and len(core) > 2:
            candidates.append(core[:-1])
        for candidate in candidates:
            if candidate and candidate in text:
                core_matches.append((candidate, item))
                break

    # 短标签或核心名称可能对应多个选项（例如两种年假余额），只有匹配结果唯一时
    # 才自动选择。
    matched_labels = {str(item.get("label") or "").strip() for _, item in core_matches}
    if len(matched_labels) != 1:
        return None
    return next(iter(matched_labels))


def _enum_option_core(label: str) -> str:
    """去掉动态选项名称中的余额/时长括号，得到可用于问答匹配的核心名。"""
    for marker in ("（", "(", "【", "["):
        if marker in label:
            return label.split(marker, 1)[0].strip()
    return label.strip()


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

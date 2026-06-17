from __future__ import annotations

from app.schemas.approval import ApprovalTemplate


def select_template_candidate(
    text: str,
    candidates: list[ApprovalTemplate],
    answer: dict[str, object] | None = None,
) -> ApprovalTemplate | None:
    """根据用户回复的序号、ID 或名称选择远程审批模板。"""
    if isinstance(answer, dict) and answer.get("field_key") == "__approval_template__":
        selected_value = str(answer.get("value") or "").strip()
        selected_label = str(answer.get("label") or "").strip()
        selected = select_template_candidate_by_text(
            selected_value or selected_label,
            candidates,
        )
        if selected:
            return selected
    return select_template_candidate_by_text(text, candidates)


def select_template_candidate_by_text(
    text: str, candidates: list[ApprovalTemplate]
) -> ApprovalTemplate | None:
    """按序号、ID、内部类型或名称匹配候选模板。"""
    cleaned = text.strip()
    if cleaned.isdigit():
        number = int(cleaned)
        if 1 <= number <= len(candidates):
            return candidates[number - 1]
    for template in candidates:
        markers = [
            template.template_id or "",
            template.approval_type,
            template.title,
            *template.aliases,
        ]
        if any(marker and marker in cleaned for marker in markers):
            return template
    return None

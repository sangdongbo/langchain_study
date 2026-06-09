from __future__ import annotations

from ai_approval_assistant.app.schemas.approval import ApprovalTemplate


def select_template_candidates(
    message: str,
    templates: list[ApprovalTemplate],
    limit: int = 8,
) -> list[ApprovalTemplate]:
    """Select a small candidate set before asking the LLM.

    Real CRM systems may expose dozens or hundreds of approval templates. We
    should not pass the entire template library to the model on every turn.
    """

    enabled_templates = [template for template in templates if template.enabled]
    scored: list[tuple[int, int, str, ApprovalTemplate]] = []
    for template in enabled_templates:
        score = _score_template(message, template)
        common_boost = 1 if template.is_common else 0
        scored.append((score, common_boost, template.title, template))

    scored.sort(key=lambda item: (-item[0], -item[1], item[3].sort_order, item[2]))
    top = [item[3] for item in scored[:limit] if item[0] > 0]
    if top:
        return top
    return sorted(enabled_templates, key=lambda item: (not item.is_common, item.sort_order, item.title))[:limit]


def _score_template(message: str, template: ApprovalTemplate) -> int:
    score = 0
    for word in {template.title, template.category, template.group_name or "", *template.aliases}:
        if word and word in message:
            score += 3
    for keyword in template.intent_keywords:
        if keyword and keyword in message:
            score += 2
    for field in template.fields:
        for option in field.options:
            if option and option in message:
                score += 1
    return score

from __future__ import annotations

import json

from ai_deep_agents_assistant.app.services.approval_service import approval_service


def get_current_user_context(user_id: str) -> str:
    """Get current user profile and organization context."""
    user = approval_service.get_user_context(user_id)
    return json.dumps(user.model_dump(), ensure_ascii=False)


def list_approval_templates(keyword: str = "") -> str:
    """List approval templates available to the current user."""
    templates = approval_service.list_templates(keyword)
    payload = [
        {
            "approval_type": template.approval_type,
            "title": template.title,
            "category": template.category,
            "aliases": template.aliases,
            "intent_keywords": template.intent_keywords,
            "required_fields": [
                {"name": field.name, "label": field.label, "question": field.question}
                for field in template.fields
                if field.required
            ],
        }
        for template in templates
    ]
    return json.dumps(payload, ensure_ascii=False)


def collect_approval_draft(
    message: str,
    approval_type: str | None = None,
    existing_slots_json: str = "{}",
) -> str:
    """Infer approval type, extract slots, and return next missing field or preview."""
    try:
        existing_slots = json.loads(existing_slots_json) if existing_slots_json else {}
    except json.JSONDecodeError:
        existing_slots = {}
    draft = approval_service.build_draft(
        message=message,
        approval_type=approval_type,
        existing_slots=existing_slots,
    )
    return json.dumps(draft.model_dump(), ensure_ascii=False)


def build_approval_preview(approval_type: str, slots_json: str) -> str:
    """Build approval preview after required fields are complete."""
    slots = json.loads(slots_json)
    preview, warnings = approval_service.build_preview(approval_type, slots)
    return json.dumps({"preview": preview.model_dump(), "warnings": warnings}, ensure_ascii=False)


def submit_approval_request(approval_type: str, slots_json: str, user_id: str) -> str:
    """Submit an approval request. This tool must be interrupted for human approval."""
    slots = json.loads(slots_json)
    result = approval_service.submit(approval_type, slots, user_id)
    return json.dumps(result.model_dump(), ensure_ascii=False)


APPROVAL_TOOLS = [
    get_current_user_context,
    list_approval_templates,
    collect_approval_draft,
    build_approval_preview,
    submit_approval_request,
]

from __future__ import annotations

import json

from ai_deep_agents_assistant.app.services.approval_service import approval_service


def get_current_user_context(user_id: str) -> str:
    """获取当前用户资料及组织上下文。"""
    user = approval_service.get_user_context(user_id)
    return json.dumps(user.model_dump(), ensure_ascii=False)


def list_approval_templates(keyword: str = "") -> str:
    """列出当前用户可用的审批模板。"""
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
    """识别审批类型、提取字段，并返回下一个待补充字段或预览。"""
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
    """在必填字段完整后生成审批预览。"""
    slots = json.loads(slots_json)
    preview, warnings = approval_service.build_preview(approval_type, slots)
    return json.dumps({"preview": preview.model_dump(), "warnings": warnings}, ensure_ascii=False)


def submit_approval_request(approval_type: str, slots_json: str, user_id: str) -> str:
    """提交审批申请；此工具必须在人工确认环节中断。"""
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

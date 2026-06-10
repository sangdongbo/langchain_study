from __future__ import annotations
import json
import logging
import os
from typing import Any
from langchain_core.messages import HumanMessage, SystemMessage
from langchain_deepseek import ChatDeepSeek
from dotenv import load_dotenv
from ai_approval_assistant.app.schemas.approval import ApprovalTemplate
from ai_approval_assistant.app.services.prompt_config_service import get_prompt_config

load_dotenv()
logger = logging.getLogger("ai_approval_assistant.model")


class ModelService:
    """审批助手使用的可选 DeepSeek 模型调用封装。"""

    def is_enabled(self) -> bool:
        """判断是否启用审批场景的 LLM 辅助能力。"""
        return os.getenv("AI_APPROVAL_USE_LLM", "false").lower() == "true"

    def chat(self, user_message: str) -> str:
        """使用已配置模型回答非审批聊天消息。"""
        if not os.getenv("DEEPSEEK_API_KEY"):
            return "你好，我可以帮你发起审批，也可以回答普通问题。需要办理审批时，直接告诉我要办什么审批和相关信息就行。"
        try:
            model = _build_deepseek()
            response = model.invoke(
                [
                    SystemMessage(
                        content="你是一个简洁友好的中文助手。用户需要办理审批时，提醒用户说明审批类型和关键信息；用户只是普通问候或普通问题时，正常回答，不要强行要求选择审批模板。"
                    ),
                    HumanMessage(content=user_message),
                ]
            )
        except Exception as exc:
            logger.warning("LLM general chat failed: %s", exc)
            return "你好，我可以帮你发起审批，也可以回答普通问题。需要办理审批时，直接告诉我要办什么审批和相关信息就行。"
        content = response.content
        if isinstance(content, list):
            content = "".join((str(item) for item in content))
        if not isinstance(content, str) or not content.strip():
            return "你好，我可以帮你发起审批，也可以回答普通问题。需要办理审批时，直接告诉我要办什么审批和相关信息就行。"
        return content.strip()

    def classify_approval_type(
        self, user_message: str, templates: list[ApprovalTemplate]
    ) -> str | None:
        """让模型从候选项中选择审批模板。"""
        if not self.is_enabled():
            return None
        available_types = {template.approval_type for template in templates}
        try:
            system, user = build_classification_prompt(user_message, templates)
            payload = self._invoke_json(system=system, user=user)
        except Exception as exc:
            logger.warning("LLM approval classification failed: %s", exc)
            return None
        approval_type = payload.get("approval_type")
        confidence = _safe_float(payload.get("confidence"), default=0)
        if approval_type in available_types and confidence >= 0.5:
            return str(approval_type)
        return None

    def extract_slots(
        self,
        template: ApprovalTemplate,
        user_message: str,
        collected_slots: dict[str, str],
        awaiting_field: str | None,
    ) -> dict[str, str]:
        """让模型从消息中抽取模板字段值。"""
        if not self.is_enabled():
            return {}
        field_names = {field.name for field in template.fields}
        try:
            system, user = build_slot_extraction_prompt(
                template=template,
                user_message=user_message,
                collected_slots=collected_slots,
                awaiting_field=awaiting_field,
            )
            payload = self._invoke_json(system=system, user=user)
        except Exception as exc:
            logger.warning("LLM slot extraction failed: %s", exc)
            return {}
        slots = payload.get("slots", {})
        if not isinstance(slots, dict):
            return {}
        return {
            key: str(value)
            for key, value in slots.items()
            if key in field_names and value
        }

    def review_decision(
        self,
        route: str,
        status: str,
        approval_type: str | None,
        user_message: str,
        templates: list[ApprovalTemplate],
    ) -> dict[str, Any]:
        """让模型复核候选工作流路由。"""
        if not self.is_enabled():
            return {}
        try:
            system, user = build_decision_review_prompt(
                route=route,
                status=status,
                approval_type=approval_type,
                user_message=user_message,
                templates=templates,
            )
            payload = self._invoke_json(system=system, user=user)
        except Exception as exc:
            logger.warning("LLM decision review failed: %s", exc)
            return {}
        route_value = payload.get("route")
        if route_value not in {"collect", "submit", "cancel", "clarify"}:
            return {}
        return {"route": route_value, "reason": str(payload.get("reason", ""))}

    def _invoke_json(self, system: str, user: dict[str, Any]) -> dict[str, Any]:
        """调用 DeepSeek 并将响应解析为 JSON 对象。"""
        model = _build_deepseek()
        response = model.invoke(
            [
                SystemMessage(content=system),
                HumanMessage(content=json.dumps(user, ensure_ascii=False)),
            ]
        )
        content = response.content
        if isinstance(content, list):
            content = "".join((str(item) for item in content))
        if not isinstance(content, str):
            raise ValueError("LLM returned non-text content")
        return _parse_json_object(content)


def build_classification_prompt(
    user_message: str, templates: list[ApprovalTemplate]
) -> tuple[str, dict[str, Any]]:
    """构建审批模板识别的提示词载荷。"""
    prompt = get_prompt_config().classification
    return (
        prompt.system,
        {
            "task": "classify_approval_type",
            "user_message": user_message,
            "candidate_templates": [
                _template_summary(template, include_fields=True)
                for template in templates
            ],
            "output_schema": prompt.output_schema,
            "decision_rules": prompt.rules,
        },
    )


def build_slot_extraction_prompt(
    template: ApprovalTemplate,
    user_message: str,
    collected_slots: dict[str, str],
    awaiting_field: str | None,
) -> tuple[str, dict[str, Any]]:
    """构建审批字段抽取的提示词载荷。"""
    prompt = get_prompt_config().slot_extraction
    return (
        prompt.system,
        {
            "task": "extract_slots",
            "approval_template": _template_summary(template, include_fields=True),
            "collected_slots": collected_slots,
            "awaiting_field": awaiting_field,
            "user_message": user_message,
            "output_schema": prompt.output_schema,
            "extraction_rules": prompt.rules,
        },
    )


def build_decision_review_prompt(
    route: str,
    status: str,
    approval_type: str | None,
    user_message: str,
    templates: list[ApprovalTemplate],
) -> tuple[str, dict[str, Any]]:
    """构建有界路由复核的提示词载荷。"""
    prompt = get_prompt_config().decision_review
    return (
        prompt.system,
        {
            "task": "review_decision",
            "candidate_route": route,
            "current_status": status,
            "approval_type": approval_type,
            "user_message": user_message,
            "candidate_templates": [
                _template_summary(template, include_fields=False)
                for template in templates
            ],
            "allowed_routes": prompt.allowed_routes,
            "output_schema": prompt.output_schema,
            "hard_rules": prompt.rules,
        },
    )


def _template_summary(
    template: ApprovalTemplate, include_fields: bool
) -> dict[str, Any]:
    """将模板转换为发送给模型的紧凑结构。"""
    summary: dict[str, Any] = {
        "template_id": template.template_id,
        "approval_type": template.approval_type,
        "title": template.title,
        "category": template.category,
        "group_name": template.group_name,
        "aliases": template.aliases,
        "intent_keywords": template.intent_keywords,
        "visibility": template.visibility,
        "is_common": template.is_common,
        "sort_order": template.sort_order,
    }
    if include_fields:
        summary["fields"] = [
            {
                "name": field.name,
                "label": field.label,
                "type": field.type,
                "required": field.required,
                "options": field.options,
                "aliases": field.aliases,
            }
            for field in template.fields
        ]
    return summary


def _build_deepseek() -> ChatDeepSeek:
    """根据环境配置创建 DeepSeek 聊天模型。"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    return ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=api_key,
        temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0")),
        timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "30")),
        max_retries=1,
    )


def _parse_json_object(text: str) -> dict[str, Any]:
    """从模型文本中提取并解析第一个 JSON 对象。"""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:].strip()
    start = cleaned.find("{")
    end = cleaned.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"LLM response is not JSON: {text[:120]}")
    parsed = json.loads(cleaned[start : end + 1])
    if not isinstance(parsed, dict):
        raise ValueError("LLM JSON root must be an object")
    return parsed


def _safe_float(value: Any, default: float) -> float:
    """将值转换为浮点数；无效时返回默认值。"""
    try:
        return float(value)
    except TypeError, ValueError:
        return default


model_service = ModelService()

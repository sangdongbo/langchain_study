from __future__ import annotations

import hashlib
import json
import re
from copy import deepcopy
from typing import Any

from ai_deep_agents_assistant.app.mock_data.approval_templates import (
    APPROVAL_TEMPLATES,
    USERS,
)
from ai_deep_agents_assistant.app.schemas.approval import (
    ApprovalDraft,
    ApprovalPreview,
    ApprovalTemplate,
    PreviewField,
    SubmitResult,
    UserContext,
)


class ApprovalService:
    """供 Deep Agent 工具调用的确定性审批后端。

    LLM 仅负责解释、规划和提问；模板定义、必填字段、校验、预览和模拟提交等
    业务规则由本服务负责。
    """

    def __init__(self) -> None:
        self._submitted_by_key: dict[str, SubmitResult] = {}

    def get_user_context(self, user_id: str) -> UserContext:
        """返回当前用户上下文。"""
        data = USERS.get(
            user_id,
            {
                "user_id": user_id,
                "name": f"User {user_id}",
                "company_id": "",
                "dept_id": "",
                "role": "",
                "manager_id": "",
            },
        )
        return UserContext(**data)

    def list_templates(self, keyword: str = "") -> list[ApprovalTemplate]:
        """列出模板，并可按关键字过滤。"""
        keyword = keyword.strip()
        templates = [ApprovalTemplate(**deepcopy(item)) for item in APPROVAL_TEMPLATES.values()]
        if not keyword:
            return templates
        return [
            template
            for template in templates
            if self._template_matches(template, keyword)
        ]

    def get_template(self, approval_type: str) -> ApprovalTemplate:
        """按审批类型获取模板。"""
        data = APPROVAL_TEMPLATES.get(approval_type)
        if not data:
            raise ValueError(f"Unknown approval_type: {approval_type}")
        return ApprovalTemplate(**deepcopy(data))

    def infer_template(self, message: str) -> ApprovalTemplate | None:
        """从用户消息中推断最匹配的模板。"""
        candidates = []
        for template in self.list_templates():
            score = 0
            markers = [template.title, template.approval_type, *template.aliases, *template.intent_keywords]
            for marker in markers:
                if marker and marker in message:
                    score += 1
            if score:
                candidates.append((score, template))
        if not candidates:
            return None
        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def build_draft(
        self,
        message: str,
        approval_type: str | None = None,
        existing_slots: dict[str, str] | None = None,
    ) -> ApprovalDraft:
        """提取字段并生成下一步审批草稿状态。"""
        template = self.get_template(approval_type) if approval_type else self.infer_template(message)
        if template is None:
            return ApprovalDraft(
                approval_type=None,
                missing_fields=[],
                next_question="你想发起哪类审批？目前支持：请假申请、报销申请、采购申请。",
            )

        slots = dict(existing_slots or {})
        slots.update(self.extract_slots(template, message))
        missing = [field.name for field in template.fields if field.required and not slots.get(field.name)]
        if missing:
            first_missing = next(field for field in template.fields if field.name == missing[0])
            return ApprovalDraft(
                approval_type=template.approval_type,
                collected_slots=slots,
                missing_fields=missing,
                next_question=first_missing.question,
            )

        preview, warnings = self.build_preview(template.approval_type, slots)
        return ApprovalDraft(
            approval_type=template.approval_type,
            collected_slots=slots,
            missing_fields=[],
            preview=preview,
            warnings=warnings,
            next_question="审批信息已收集完整。请确认是否提交，明确回复“确认提交”后才会创建审批。",
        )

    def extract_slots(self, template: ApprovalTemplate, message: str) -> dict[str, str]:
        """使用模板正则及少量规则兜底提取表单字段。"""
        slots: dict[str, str] = {}
        for field in template.fields:
            for option in field.options:
                if option in message:
                    slots[field.name] = option
                    break
            if slots.get(field.name):
                continue
            for pattern in field.extract_patterns:
                match = re.search(pattern, message)
                if match:
                    slots[field.name] = self._clean_value(match.group(1))
                    break

        if template.approval_type == "expense":
            if "发票" in message and "invoice" not in slots:
                slots["invoice"] = "已提供" if "已" in message or "有" in message else "待补充"
        return slots

    def validate(self, approval_type: str, slots: dict[str, str]) -> tuple[bool, list[str], list[str]]:
        """校验必填字段和基础业务规则。"""
        template = self.get_template(approval_type)
        errors: list[str] = []
        warnings: list[str] = []
        for field in template.fields:
            value = slots.get(field.name, "")
            if field.required and not value:
                errors.append(f"{field.label}不能为空。")
            if field.type == "enum" and value and value not in field.options:
                errors.append(f"{field.label}必须是：{', '.join(field.options)}。")
            if field.type == "number" and value and self._safe_number(value) <= 0:
                errors.append(f"{field.label}必须大于 0。")
        if approval_type == "leave" and slots.get("start_date") and slots.get("end_date"):
            if slots["start_date"] > slots["end_date"]:
                errors.append("开始时间不能晚于结束时间。")
        if approval_type == "expense" and self._safe_number(slots.get("amount", "0")) >= 5000:
            warnings.append("报销金额较高，将进入部门负责人审批。")
        return not errors, errors, warnings

    def build_preview(self, approval_type: str, slots: dict[str, str]) -> tuple[ApprovalPreview, list[str]]:
        """生成提交预览。"""
        valid, errors, warnings = self.validate(approval_type, slots)
        if not valid:
            raise ValueError("; ".join(errors))
        template = self.get_template(approval_type)
        fields = [
            PreviewField(name=field.name, label=field.label, value=str(slots.get(field.name, "")))
            for field in template.fields
        ]
        preview = ApprovalPreview(
            approval_type=approval_type,
            title=template.title,
            fields=fields,
            approval_node=self._approval_node(approval_type, slots),
            warnings=warnings,
        )
        return preview, warnings

    def submit(self, approval_type: str, slots: dict[str, str], user_id: str) -> SubmitResult:
        """执行带幂等保障的模拟审批提交。"""
        preview, _ = self.build_preview(approval_type, slots)
        idempotency_key = self._idempotency_key(user_id, approval_type, slots)
        if idempotency_key in self._submitted_by_key:
            return self._submitted_by_key[idempotency_key]
        digest = hashlib.sha1(idempotency_key.encode("utf-8")).hexdigest()[:8]
        result = SubmitResult(
            request_id=f"APR-{digest.upper()}",
            status="submitted",
            approval_node=preview.approval_node,
            idempotency_key=idempotency_key,
        )
        self._submitted_by_key[idempotency_key] = result
        return result

    def _template_matches(self, template: ApprovalTemplate, keyword: str) -> bool:
        markers = [template.title, template.category, template.approval_type, *template.aliases, *template.intent_keywords]
        return any(marker and keyword in marker for marker in markers)

    def _approval_node(self, approval_type: str, slots: dict[str, str]) -> str:
        if approval_type == "expense" and self._safe_number(slots.get("amount", "0")) >= 5000:
            return "部门负责人 -> 财务经理"
        if approval_type == "purchase" and self._safe_number(slots.get("budget", "0")) >= 10000:
            return "直属上级 -> 行政负责人 -> 财务经理"
        return "直属上级"

    def _idempotency_key(self, user_id: str, approval_type: str, slots: dict[str, str]) -> str:
        payload = json.dumps({"user_id": user_id, "approval_type": approval_type, "slots": slots}, sort_keys=True, ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def _clean_value(self, value: str) -> str:
        return value.strip(" ，,。；;")

    def _safe_number(self, value: Any) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0


approval_service = ApprovalService()

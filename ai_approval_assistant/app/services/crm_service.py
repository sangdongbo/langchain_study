from __future__ import annotations

from datetime import datetime

from ai_approval_assistant.app.mock_data.approval_templates import APPROVAL_TEMPLATES, USERS
from ai_approval_assistant.app.schemas.approval import (
    ApprovalTemplate,
    FieldError,
    SubmitResult,
    UserContext,
    ValidationResult,
)


class CrmApprovalService:
    """CRM adapter boundary.

    Current implementation uses local mock data. Real CRM HTTP calls should replace
    methods in this class without changing graph or API layers.
    """

    def __init__(self) -> None:
        self._submitted_by_key: dict[str, SubmitResult] = {}

    def get_user_context(self, user_id: str) -> UserContext:
        user = USERS.get(user_id)
        if user is None:
            raise ValueError(f"Unknown user_id: {user_id}")
        return UserContext(**user)

    def list_available_templates(self, user: UserContext) -> list[ApprovalTemplate]:
        return [ApprovalTemplate(**template) for template in APPROVAL_TEMPLATES.values()]

    def get_template_detail(self, approval_type: str, user: UserContext) -> ApprovalTemplate:
        template = APPROVAL_TEMPLATES.get(approval_type)
        if template is None:
            raise ValueError(f"Unknown approval_type: {approval_type}")
        return ApprovalTemplate(**template)

    def validate_approval(
        self,
        approval_type: str,
        slots: dict[str, str],
        user: UserContext,
    ) -> ValidationResult:
        template = self.get_template_detail(approval_type, user)
        errors: list[str] = []
        field_errors: list[FieldError] = []
        warnings: list[str] = []

        for field in template.fields:
            value = slots.get(field.name, "")
            if field.required and not value:
                message = f"{field.label}不能为空。"
                errors.append(message)
                field_errors.append(FieldError(field=field.name, message=message))
            if field.type == "enum" and value and value not in field.options:
                message = f"{field.label}必须是：{', '.join(field.options)}。"
                errors.append(message)
                field_errors.append(FieldError(field=field.name, message=message))
            if field.type == "number" and value and _safe_number(value) <= 0:
                message = f"{field.label}必须大于 0。"
                errors.append(message)
                field_errors.append(FieldError(field=field.name, message=message))

        if approval_type == "leave":
            start_date = slots.get("start_date", "")
            end_date = slots.get("end_date", "")
            if start_date and end_date and start_date > end_date:
                message = "开始时间不能晚于结束时间。"
                errors.append(message)
                field_errors.append(FieldError(field="start_date", message=message))
                field_errors.append(FieldError(field="end_date", message=message))

        if approval_type == "expense" and _safe_number(slots.get("amount", "0")) >= 5000:
            warnings.append("报销金额较高，将进入部门负责人审批。")

        approval_node = _approval_node(approval_type, slots)
        return ValidationResult(
            valid=not errors,
            errors=errors,
            field_errors=field_errors,
            warnings=warnings,
            approval_node=approval_node,
        )

    def submit_approval(
        self,
        approval_type: str,
        slots: dict[str, str],
        user: UserContext,
        idempotency_key: str,
    ) -> SubmitResult:
        if idempotency_key in self._submitted_by_key:
            return self._submitted_by_key[idempotency_key]

        prefix = {
            "leave": "LR",
            "expense": "EX",
            "purchase": "PR",
            "seal": "SE",
        }.get(approval_type, "AP")
        result = SubmitResult(
            request_id=f"{prefix}-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            status="待审批",
            approval_node=_approval_node(approval_type, slots),
            idempotency_key=idempotency_key,
        )
        self._submitted_by_key[idempotency_key] = result
        return result


def _approval_node(approval_type: str, slots: dict[str, str]) -> str:
    if approval_type == "expense" and _safe_number(slots.get("amount", "0")) >= 5000:
        return "部门负责人审批"
    if approval_type == "purchase" and _safe_number(slots.get("budget", "0")) >= 10000:
        return "采购主管审批"
    if approval_type == "seal":
        return "行政负责人审批"
    return "直属主管审批"


def _safe_number(value: str) -> float:
    digits = "".join(ch for ch in str(value) if ch.isdigit() or ch == ".")
    if not digits:
        return 0.0
    return float(digits)


crm_approval_service = CrmApprovalService()

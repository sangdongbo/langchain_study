from __future__ import annotations

from app.agents import approval_agent
from app.graph.extractors import extract_slots
from app.graph.state import initial_state
from app.schemas.approval import ApprovalField, ApprovalTemplate


def test_extract_slots_matches_dynamic_enum_core_label() -> None:
    template = ApprovalTemplate(
        approval_type="remote_leave",
        title="请假",
        category="人事",
        fields=[
            ApprovalField(
                name="rest_holiday_rule_id",
                label="请假类型",
                type="enum",
                options=["年假（10天）", "事假"],
                option_values=[
                    {"label": "年假（10天）", "value": 12},
                    {"label": "事假", "value": 13},
                ],
                question="请选择请假类型",
            )
        ],
    )

    slots = extract_slots(template, "我要请假，从明天开始请3天年假，原因是家中有事。")

    assert slots["rest_holiday_rule_id"] == "年假（10天）"


def test_extract_slots_does_not_guess_ambiguous_enum_core_label() -> None:
    template = ApprovalTemplate(
        approval_type="remote_leave",
        title="请假",
        category="人事",
        fields=[
            ApprovalField(
                name="rest_holiday_rule_id",
                label="请假类型",
                type="enum",
                options=["年假（10天）", "年假（余5天）"],
                question="请选择请假类型",
            )
        ],
    )

    slots = extract_slots(template, "我要请年假")

    assert "rest_holiday_rule_id" not in slots


def test_collect_node_keeps_dynamic_enum_value_after_text_match(monkeypatch) -> None:
    template = ApprovalTemplate(
        approval_type="remote_leave",
        title="请假",
        category="人事",
        fields=[
            ApprovalField(
                name="rest_holiday_rule_id",
                label="请假类型",
                type="enum",
                options=["年假（10天）", "事假"],
                option_values=[
                    {"label": "年假（10天）", "value": 12},
                    {"label": "事假", "value": 13},
                ],
                question="请选择请假类型",
            )
        ],
    )
    monkeypatch.setattr(
        approval_agent.crm_approval_service,
        "get_template_detail",
        lambda approval_type, user: template,
    )
    monkeypatch.setattr(
        approval_agent.model_service,
        "extract_slots",
        lambda **kwargs: {},
    )
    state = initial_state("test-session", "U001")
    state.update(
        {
            "approval_type": "remote_leave",
            "user_message": "我要请3天年假",
        }
    )

    result = approval_agent.collect_node(state)

    assert result["collected_slots"]["rest_holiday_rule_id"] == "年假（10天）"
    assert result["collected_values"]["rest_holiday_rule_id"] == {
        "label": "年假（10天）",
        "value": 12,
    }
    assert result["awaiting_field"] is None

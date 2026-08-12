from __future__ import annotations

from app.agents.approval.state_helpers import form_value_from_state


def test_form_value_from_state_prefers_structured_erp_values() -> None:
    result = form_value_from_state(
        {
            "collected_slots": {
                "rest_holiday_rule_id": "年假（10天）",
                "rest_start_time": "2026-08-12 09:00",
                "rest_content": "请假了",
            },
            "collected_values": {
                "rest_holiday_rule_id": {"label": "年假（10天）", "value": 12},
                "rest_start_time": {
                    "label": "2026-08-12 09:00",
                    "value": "2026-08-12 09:00:00",
                },
            },
        }
    )

    assert result == [
        {"field_key": "rest_holiday_rule_id", "value": 12},
        {"field_key": "rest_start_time", "value": "2026-08-12 09:00:00"},
        {"field_key": "rest_content", "value": "请假了"},
    ]

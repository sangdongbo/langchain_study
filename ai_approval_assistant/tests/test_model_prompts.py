from __future__ import annotations

import json

from ai_approval_assistant.app.mock_data.approval_templates import APPROVAL_TEMPLATES
from ai_approval_assistant.app.schemas.approval import ApprovalTemplate
from ai_approval_assistant.app.services.model_service import (
    build_classification_prompt,
    build_decision_review_prompt,
    build_slot_extraction_prompt,
)
from ai_approval_assistant.app.services.prompt_config_service import reload_prompt_config


def _template(name: str) -> ApprovalTemplate:
    return ApprovalTemplate(**APPROVAL_TEMPLATES[name])


def test_classification_prompt_uses_candidate_templates_and_ambiguity_rules() -> None:
    system, user = build_classification_prompt(
        user_message="我要处理一份销售合同，盖两份",
        templates=[_template("seal"), _template("purchase")],
    )

    assert "候选审批模板" in system
    assert user["task"] == "classify_approval_type"
    assert len(user["candidate_templates"]) == 2
    assert user["candidate_templates"][0]["template_id"] == "tpl_seal_001"
    assert any("无法区分" in rule for rule in user["decision_rules"])


def test_slot_prompt_limits_output_to_current_template_fields() -> None:
    system, user = build_slot_extraction_prompt(
        template=_template("seal"),
        user_message="文件名称是销售合同，2份",
        collected_slots={},
        awaiting_field="seal_type",
    )

    assert "不能根据常识补全" in system
    assert user["approval_template"]["approval_type"] == "seal"
    field_names = {field["name"] for field in user["approval_template"]["fields"]}
    assert field_names == {"seal_type", "document_name", "copies", "purpose"}
    assert any("不要覆盖" in rule for rule in user["extraction_rules"])


def test_decision_review_prompt_keeps_submit_guardrails() -> None:
    system, user = build_decision_review_prompt(
        route="submit",
        status="collecting",
        approval_type="seal",
        user_message="好的",
        templates=[_template("seal")],
    )

    assert "硬性规则优先" in system
    assert user["candidate_route"] == "submit"
    assert "submit" in user["allowed_routes"]
    assert any("没有审批预览" in rule for rule in user["hard_rules"])
    assert any("好的" in rule for rule in user["hard_rules"])


def test_prompt_builders_can_use_custom_prompt_file(tmp_path, monkeypatch) -> None:
    prompt_file = tmp_path / "approval_prompts.json"
    prompt_file.write_text(
        json.dumps(
            {
                "version": "test",
                "classification": {
                    "system": "自定义分类提示词",
                    "output_schema": {"approval_type": "string or null"},
                    "rules": ["自定义分类规则"],
                },
                "slot_extraction": {
                    "system": "自定义字段抽取提示词",
                    "output_schema": {"slots": {"field_name": "field_value"}},
                    "rules": ["自定义抽取规则"],
                },
                "decision_review": {
                    "system": "自定义复核提示词",
                    "allowed_routes": ["collect", "submit", "cancel", "clarify"],
                    "output_schema": {"route": "string"},
                    "rules": ["自定义复核规则"],
                },
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    monkeypatch.setenv("AI_APPROVAL_PROMPT_FILE", str(prompt_file))
    reload_prompt_config()

    system, user = build_classification_prompt(
        user_message="我要用章",
        templates=[_template("seal")],
    )

    assert system == "自定义分类提示词"
    assert user["decision_rules"] == ["自定义分类规则"]

    monkeypatch.delenv("AI_APPROVAL_PROMPT_FILE")
    reload_prompt_config()

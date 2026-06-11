from __future__ import annotations

from app.services.crm_config_service import (
    load_crm_endpoint_config,
)


def test_crm_endpoint_config_uses_base_url(monkeypatch) -> None:
    """CRM base URL 应统一拼接审批相关接口地址。"""
    monkeypatch.setenv("AI_APPROVAL_CRM_BASE_URL", "http://crm.local:8002/")
    monkeypatch.delenv("AI_APPROVAL_LIST_URL", raising=False)
    monkeypatch.delenv("AI_APPROVAL_FORM_FIELDS_URL", raising=False)
    monkeypatch.delenv("AI_APPROVAL_GET_NODES_URL", raising=False)
    monkeypatch.delenv("AI_APPROVAL_ADD_URL", raising=False)
    monkeypatch.delenv("AI_APPROVAL_RELATED_LIST_URL", raising=False)
    monkeypatch.delenv("AI_APPROVAL_HOLIDAY_RULE_URL", raising=False)

    config = load_crm_endpoint_config()

    assert config.approval_list_url == "http://crm.local:8002/api/approval/list"
    assert config.form_fields_url == "http://crm.local:8002/api/field/formFields"
    assert config.get_nodes_url == "http://crm.local:8002/api/approval/getNodes"
    assert config.add_approval_url == "http://crm.local:8002/api/approval/add"
    assert config.related_list_url == "http://crm.local:8002/api/Company/getRelatedList"
    assert config.holiday_rule_url == "http://crm.local:8002/api/attendance/getHolidayRuleByUser"


def test_crm_endpoint_config_keeps_specific_url_override(monkeypatch) -> None:
    """单个接口 URL 配置应优先于 base URL 拼接结果。"""
    monkeypatch.setenv("AI_APPROVAL_CRM_BASE_URL", "http://crm.local:8002")
    monkeypatch.setenv("AI_APPROVAL_LIST_URL", "http://override/api/approval/list")

    config = load_crm_endpoint_config()

    assert config.approval_list_url == "http://override/api/approval/list"
    assert config.form_fields_url == "http://crm.local:8002/api/field/formFields"

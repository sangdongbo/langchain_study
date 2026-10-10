"""客户管理 Agent 的只读边界与日期范围测试。"""

from datetime import date

import pytest

from ai_erp_rag_assistant.app.agents import harness as harness_module
from ai_erp_rag_assistant.app.services.erp_client import ErpClient
from ai_erp_rag_assistant.app.tools.customer import state_tools


def test_customer_date_range_supports_common_business_phrases():
    today = date(2026, 10, 10)

    assert state_tools.customer_activity_date_range("今天客户动态", today=today) == [
        "2026-10-10",
        "2026-10-10",
    ]
    assert state_tools.customer_activity_date_range("本周客户跟进", today=today) == [
        "2026-10-05",
        "2026-10-10",
    ]
    assert state_tools.customer_activity_date_range("查询 2026-10-01 到 2026-10-03", today=today) == [
        "2026-10-01",
        "2026-10-03",
    ]
    with pytest.raises(ValueError, match="31 天"):
        state_tools.customer_activity_date_range(
            "查询 2026-01-01 到 2026-03-01",
            today=today,
        )


def test_customer_state_tool_uses_verified_user(monkeypatch):
    captured = {}

    monkeypatch.setattr(
        state_tools,
        "get_customer_activity",
        lambda query, date_range, *, user: captured.update(
            query=query,
            date_range=date_range,
            user=user,
        ) or {"items": []},
    )
    result = state_tools.query_customer_activity_from_state(
        {
            "user_message": "查询 2026-10-01 的客户跟进",
            "company_id": "伪造公司",
            "user_context": {"company_id": "16", "uid": "863"},
        }
    )

    assert result == {"items": []}
    assert captured["date_range"] == ["2026-10-01", "2026-10-01"]
    assert captured["user"]["company_id"] == "16"


def test_customer_harness_only_registers_customer_subagent(monkeypatch):
    captured = {}
    monkeypatch.setattr(
        harness_module,
        "create_deep_agent",
        lambda **kwargs: captured.update(kwargs) or "compiled-harness",
    )

    result = harness_module.create_erp_agent_harness(
        assistant_type="customer",
        model=object(),
    )

    assert result == "compiled-harness"
    assert [item["name"] for item in captured["subagents"]] == [
        "customer-management"
    ]
    assert "没有 ERP 返回数据时不得编造客户信息" in captured["system_prompt"]


def test_customer_client_calls_read_only_customer_activity_endpoint(monkeypatch):
    client = ErpClient()
    captured = {}
    monkeypatch.setattr(type(client), "read_mode", property(lambda _self: "remote"))
    monkeypatch.setattr(
        client,
        "_post",
        lambda path, body, user: captured.update(
            path=path,
            body=body,
            user=user,
        ) or {"code": 200, "data": [{"customer_name": "测试客户"}]},
    )

    result = client.get_customer_activity(
        "本周客户跟进",
        ["2026-10-05", "2026-10-10"],
        user={"company_id": "16", "uid": "863"},
    )

    assert captured["path"] == client.settings.erp_customer_activity_path
    assert captured["body"] == {
        "daily_report_type": 1,
        "sync_type": ["customer_manage"],
        "date_range": ["2026-10-05", "2026-10-10"],
    }
    assert result["items"] == [{"customer_name": "测试客户"}]
    assert result["count"] == 1

"""State 工具适配层的权限与冻结预览单元测试。"""

import pytest

from ai_erp_rag_assistant.app.repositories.rag_admin import RagRuntimeConfig
from ai_erp_rag_assistant.app.tools.approval import state_tools as approval_state_tools
from ai_erp_rag_assistant.app.tools.erp import state_tools as erp_state_tools
from ai_erp_rag_assistant.app.tools.rag import retrieve as rag_retrieve


def test_rag_state_tool_only_uses_verified_identity(monkeypatch):
    """状态外层的伪造租户和权限不能覆盖 ERP 已验证身份。"""
    captured = {}

    def fake_search(query, **kwargs):
        captured.update({"query": query, **kwargs})
        return [{"text": "命中内容"}]

    monkeypatch.setattr(rag_retrieve, "search_knowledge", fake_search)
    runtime = RagRuntimeConfig(collection="company_16_hr", top_k=7)

    result = rag_retrieve.retrieve_from_state(
        {
            "query": "外层问题",
            "user_message": "原始问题",
            "company_id": "伪造公司",
            "department": "伪造部门",
            "permission_tags": ["admin"],
            "user_context": {
                "company_id": "16",
                "department": "人事部",
                "rag_access_tags": ["hr:read"],
            },
        },
        runtime=runtime,
    )

    assert result == [{"text": "命中内容"}]
    assert captured["company_id"] == "16"
    assert captured["department"] == "人事部"
    assert captured["permission_tags"] == ["hr:read"]
    assert captured["query"] == "外层问题"
    assert captured["top_k"] == 7


def test_rag_state_tool_rejects_unverified_identity():
    """只有请求体身份而没有 user_context 时必须拒绝检索。"""
    with pytest.raises(PermissionError, match="user_context"):
        rag_retrieve.retrieve_from_state(
            {
                "query": "测试",
                "company_id": "16",
                "permission_tags": ["admin"],
            }
        )


def test_erp_status_state_tool_uses_verified_user(monkeypatch):
    """状态查询使用可信用户 ID，不使用状态外层可覆盖的 user_id。"""
    captured = {}

    def fake_query(user_id, *, user):
        captured.update({"user_id": user_id, "user": user})
        return {"pending": 2}

    monkeypatch.setattr(erp_state_tools, "query_approval_status", fake_query)
    result = erp_state_tools.query_approval_status_from_state(
        {
            "user_id": "伪造用户",
            "user_context": {"uid": "863", "company_id": "16"},
        }
    )

    assert result == {"pending": 2}
    assert captured["user_id"] == "863"
    assert captured["user"]["company_id"] == "16"


def test_approval_submit_requires_frozen_preview():
    """没有冻结预览时，即使 confirm=true 也不能进入 ERP 写入。"""
    with pytest.raises(ValueError, match="preview"):
        approval_state_tools.submit_confirmed_preview_from_state(
            {
                "confirm": True,
                "user_context": {"uid": "863", "company_id": "16"},
            }
        )


def test_approval_submit_uses_state_preview_and_verified_user(monkeypatch):
    """提交参数只能来自冻结预览和已验证身份。"""
    captured = {}

    def fake_submit(preview, *, user):
        captured.update({"preview": preview, "user": user})
        return {"approval_id": "A-1"}

    monkeypatch.setattr(approval_state_tools, "submit_approval", fake_submit)
    preview = {
        "preview_id": "preview-1",
        "preview_version": 3,
        "preview_hash": "hash-1",
        "idempotency_key": "idempotency-1",
        "template_id": "5911",
        "submission_fields": {"reason": "就医"},
        "requires_confirmation": True,
    }
    result = approval_state_tools.submit_confirmed_preview_from_state(
        {
            "confirm": True,
            "confirm_preview_id": "preview-1",
            "confirm_preview_version": 3,
            "confirm_preview_hash": "hash-1",
            "company_id": "伪造公司",
            "preview": preview,
            "user_context": {
                "uid": "863",
                "company_id": "16",
                "authorization": "Bearer verified",
            },
        }
    )

    assert result == {"approval_id": "A-1"}
    assert captured["preview"] == preview
    assert captured["preview"] is not preview
    assert captured["user"]["company_id"] == "16"


def test_approval_submit_rejects_stale_confirmation(monkeypatch):
    """客户端确认的是旧预览时，ERP 提交函数不能被调用。"""
    monkeypatch.setattr(
        approval_state_tools,
        "submit_approval",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("不应提交")),
    )

    with pytest.raises(ValueError, match="预览内容已变化"):
        approval_state_tools.submit_confirmed_preview_from_state(
            {
                "confirm": True,
                "confirm_preview_hash": "old-hash",
                "preview": {
                    "preview_id": "preview-1",
                    "preview_hash": "new-hash",
                    "idempotency_key": "idempotency-1",
                },
                "user_context": {"uid": "863", "company_id": "16"},
            }
        )

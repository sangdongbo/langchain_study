from __future__ import annotations

import os

os.environ["AI_APPROVAL_USE_LLM"] = "false"
os.environ["AI_APPROVAL_SESSION_BACKEND"] = "memory"

from fastapi.testclient import TestClient

from app.main import app
from app.services.session_state_service import session_state_service


client = TestClient(app)


def test_chat_turns_create_listable_checkpoints() -> None:
    session_id = "time-travel-list"
    user_id = "u-time-travel"
    _clear_session(session_id)

    _post_chat(session_id, user_id, "我要请假")
    _post_chat(session_id, user_id, "年假")

    response = client.get(
        f"/api/ai-approval/time-travel/{session_id}/checkpoints",
        params={"user_id": user_id},
    )

    assert response.status_code == 200
    checkpoints = response.json()
    assert len(checkpoints) == 2
    assert checkpoints[0]["turn_index"] == 1
    assert checkpoints[1]["turn_index"] == 2
    assert checkpoints[0]["message"] == "我要请假"
    assert checkpoints[0]["trace"][:2] == ["memory_agent", "intent_router"]
    assert checkpoints[0]["summary"]


def test_checkpoint_detail_restore_and_fork_session_state() -> None:
    session_id = "time-travel-restore"
    fork_session_id = "time-travel-fork"
    user_id = "u-time-travel"
    _clear_session(session_id)
    _clear_session(fork_session_id)

    _post_chat(session_id, user_id, "我要请假")
    _post_chat(session_id, user_id, "年假")

    checkpoints = client.get(
        f"/api/ai-approval/time-travel/{session_id}/checkpoints",
        params={"user_id": user_id},
    ).json()
    first_checkpoint_id = checkpoints[0]["checkpoint_id"]

    detail = client.get(
        f"/api/ai-approval/time-travel/{session_id}/checkpoints/{first_checkpoint_id}",
        params={"user_id": user_id},
    )
    assert detail.status_code == 200
    detail_payload = detail.json()
    assert detail_payload["checkpoint_id"] == first_checkpoint_id
    assert detail_payload["state"]["session_id"] == session_id
    assert detail_payload["state"]["user_message"] == "我要请假"

    restore = client.post(
        f"/api/ai-approval/time-travel/{session_id}/restore",
        json={"checkpoint_id": first_checkpoint_id, "user_id": user_id},
    )
    assert restore.status_code == 200
    restored = restore.json()
    assert restored["session_id"] == session_id
    assert restored["state"]["user_message"] == "我要请假"
    assert restored["state"]["session_id"] == session_id
    assert session_state_service.load(session_id, user_id)["user_message"] == "我要请假"

    fork = client.post(
        f"/api/ai-approval/time-travel/{session_id}/fork",
        json={
            "checkpoint_id": first_checkpoint_id,
            "user_id": user_id,
            "new_session_id": fork_session_id,
        },
    )
    assert fork.status_code == 200
    forked = fork.json()
    assert forked["session_id"] == fork_session_id
    assert forked["source_session_id"] == session_id
    assert forked["state"]["session_id"] == fork_session_id
    assert forked["state"]["user_message"] == "我要请假"
    assert session_state_service.load(fork_session_id, user_id)["user_message"] == "我要请假"


def test_unknown_checkpoint_returns_404() -> None:
    session_id = "time-travel-missing"
    user_id = "u-time-travel"
    _clear_session(session_id)

    response = client.get(
        f"/api/ai-approval/time-travel/{session_id}/checkpoints/not-found",
        params={"user_id": user_id},
    )

    assert response.status_code == 404


def _post_chat(session_id: str, user_id: str, message: str) -> None:
    response = client.post(
        "/api/ai-approval/chat",
        json={"session_id": session_id, "user_id": user_id, "message": message},
    )
    assert response.status_code == 200


def _clear_session(session_id: str) -> None:
    session_state_service.clear(session_id)

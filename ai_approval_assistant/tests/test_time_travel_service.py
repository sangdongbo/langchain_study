from __future__ import annotations

from app.graph.state import initial_state
from app.services.time_travel_service import (
    RedisTimeTravelService,
    TimeTravelService,
    build_time_travel_service,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.expirations: dict[str, int] = {}
        self.ping_called = False

    def ping(self) -> bool:
        self.ping_called = True
        return True

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.expirations[key] = ex

    def delete(self, key: str) -> None:
        self.values.pop(key, None)
        self.expirations.pop(key, None)


def test_redis_time_travel_service_persists_checkpoints_as_json() -> None:
    redis = FakeRedis()
    service = RedisTimeTravelService(redis, key_prefix="test:", ttl_seconds=30)
    state = initial_state("S-redis", "U-redis")
    state["user_message"] = "我要请假"
    state["authorization"] = "Bearer secret"
    state["trace"] = ["memory_agent", "intent_router"]

    checkpoint = service.record(state, user_message="我要请假")
    listed = service.list("S-redis", "U-redis")
    detail = service.get("S-redis", checkpoint.checkpoint_id, "U-redis")
    restored = service.restore("S-redis", checkpoint.checkpoint_id, "U-redis")

    assert listed[0].checkpoint_id == checkpoint.checkpoint_id
    assert listed[0].turn_index == 1
    assert detail is not None
    assert detail.state["authorization"] == "***REDACTED***"
    assert restored is not None
    assert restored["authorization"] == "Bearer secret"
    assert redis.expirations["test:ai_approval:checkpoints:S-redis"] == 30


def test_redis_time_travel_service_forks_and_clears_checkpoint_state() -> None:
    redis = FakeRedis()
    service = RedisTimeTravelService(redis, key_prefix="test:")
    state = initial_state("S-source", "U-redis")
    state["user_message"] = "原始状态"

    checkpoint = service.record(state)
    forked = service.fork(
        "S-source",
        checkpoint.checkpoint_id,
        "U-redis",
        "S-fork",
    )
    service.clear("S-source")

    assert forked is not None
    assert forked["session_id"] == "S-fork"
    assert forked["user_message"] == "原始状态"
    assert service.list("S-source", "U-redis") == []


def test_build_time_travel_service_uses_memory_when_backend_is_memory(monkeypatch) -> None:
    monkeypatch.setenv("AI_APPROVAL_CHECKPOINT_BACKEND", "memory")

    service = build_time_travel_service()

    assert isinstance(service, TimeTravelService)

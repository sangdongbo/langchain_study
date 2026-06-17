from __future__ import annotations

import json

from app.graph.state import initial_state
from app.services.session_state_service import (
    InMemorySessionStateService,
    RedisSessionStateService,
    build_session_state_service,
)


class FakeRedis:
    def __init__(self) -> None:
        self.values: dict[str, str] = {}
        self.ttls: dict[str, int] = {}

    def setex(self, key: str, ttl: int, value: str) -> None:
        self.values[key] = value
        self.ttls[key] = ttl

    def set(self, key: str, value: str, ex: int | None = None) -> None:
        self.values[key] = value
        if ex is not None:
            self.ttls[key] = ex

    def get(self, key: str) -> str | None:
        return self.values.get(key)

    def delete(self, key: str) -> None:
        self.values.pop(key, None)


def test_redis_session_state_service_saves_with_prefix_and_ttl() -> None:
    client = FakeRedis()
    service = RedisSessionStateService(
        redis_client=client,
        key_prefix="lanerp20_local_",
        ttl_seconds=7200,
    )
    state = initial_state("S-redis", "U001")
    state["status"] = "collecting"
    state["approval_type"] = "purchase"
    state["collected_slots"] = {"item": "笔记本电脑"}
    state["short_term_memory"] = [{"role": "user", "content": "我要采购"}]

    service.save(state)

    key = "lanerp20_local_ai_approval:session:S-redis"
    assert client.ttls[key] == 7200
    assert json.loads(client.values[key])["approval_type"] == "purchase"
    assert json.loads(client.values[key])["short_term_memory"][0]["content"] == "我要采购"


def test_redis_session_state_service_loads_existing_state_and_refreshes_user() -> None:
    client = FakeRedis()
    key = "lanerp20_local_ai_approval:session:S-redis"
    state = initial_state("S-redis", "U001")
    state["status"] = "collecting"
    state["short_term_memory"] = [{"role": "user", "content": "上一轮消息"}]
    client.values[key] = json.dumps(state, ensure_ascii=False)
    service = RedisSessionStateService(
        redis_client=client,
        key_prefix="lanerp20_local_",
        ttl_seconds=7200,
    )

    loaded = service.load("S-redis", "U002")

    assert loaded["session_id"] == "S-redis"
    assert loaded["user_id"] == "U002"
    assert loaded["status"] == "collecting"
    assert loaded["short_term_memory"][0]["content"] == "上一轮消息"


def test_redis_session_state_service_falls_back_to_initial_state_on_bad_payload() -> None:
    client = FakeRedis()
    client.values["ai_approval:session:S-bad"] = "{bad json"
    service = RedisSessionStateService(redis_client=client, key_prefix="", ttl_seconds=7200)

    loaded = service.load("S-bad", "U001")

    assert loaded == initial_state("S-bad", "U001")


def test_build_session_state_service_returns_memory_when_redis_disabled(monkeypatch) -> None:
    monkeypatch.setenv("AI_APPROVAL_SESSION_BACKEND", "memory")

    service = build_session_state_service()

    assert isinstance(service, InMemorySessionStateService)


def test_build_session_state_service_uses_configured_redis_protocol(
    monkeypatch,
) -> None:
    created_clients: list[dict[str, object]] = []

    class FakeRedisClient:
        def __init__(self, **kwargs) -> None:
            created_clients.append(kwargs)

        def ping(self) -> None:
            return None

    monkeypatch.setenv("AI_APPROVAL_SESSION_BACKEND", "redis")
    monkeypatch.setenv("REDIS_HOST", "redis.local")
    monkeypatch.setenv("REDIS_PORT", "6379")
    monkeypatch.setenv("REDIS_PROTOCOL", "2")
    monkeypatch.setattr("redis.Redis", FakeRedisClient)

    service = build_session_state_service()

    assert isinstance(service, RedisSessionStateService)
    assert created_clients[0]["protocol"] == 2

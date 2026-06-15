from __future__ import annotations

from copy import deepcopy
import json
import logging
import os
from typing import Any, Protocol

from app.graph.state import ApprovalState, initial_state

logger = logging.getLogger("ai_approval_assistant.session")

DEFAULT_SESSION_TTL_SECONDS = 7200


class SessionStateService(Protocol):
    def load(self, session_id: str, user_id: str) -> ApprovalState:
        ...

    def save(self, state: ApprovalState) -> None:
        ...

    def clear(self, session_id: str) -> None:
        ...


class InMemorySessionStateService:
    """临时会话存储；未启用 Redis 或 Redis 不可用时使用。"""

    def __init__(self) -> None:
        self._states: dict[str, ApprovalState] = {}

    def load(self, session_id: str, user_id: str) -> ApprovalState:
        state = self._states.get(session_id)
        if state is None:
            return initial_state(session_id=session_id, user_id=user_id)
        loaded = deepcopy(state)
        loaded["user_id"] = user_id
        return loaded

    def save(self, state: ApprovalState) -> None:
        self._states[state["session_id"]] = deepcopy(state)

    def clear(self, session_id: str) -> None:
        self._states.pop(session_id, None)


class RedisSessionStateService:
    """Redis 会话存储，按 TTL 保存审批流程上下文。"""

    def __init__(
        self,
        redis_client: Any,
        key_prefix: str = "",
        ttl_seconds: int = DEFAULT_SESSION_TTL_SECONDS,
    ) -> None:
        self._redis = redis_client
        self._key_prefix = key_prefix or ""
        self._ttl_seconds = max(1, ttl_seconds)

    def load(self, session_id: str, user_id: str) -> ApprovalState:
        try:
            payload = self._redis.get(self._key(session_id))
        except Exception as exc:
            logger.warning("Redis session load failed: %s", exc)
            return initial_state(session_id=session_id, user_id=user_id)
        if payload is None:
            return initial_state(session_id=session_id, user_id=user_id)
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        try:
            state = json.loads(str(payload))
        except (TypeError, ValueError) as exc:
            logger.warning("Redis session payload invalid: %s", exc)
            return initial_state(session_id=session_id, user_id=user_id)
        if not isinstance(state, dict):
            return initial_state(session_id=session_id, user_id=user_id)
        loaded = deepcopy(state)
        loaded["session_id"] = session_id
        loaded["user_id"] = user_id
        return loaded

    def save(self, state: ApprovalState) -> None:
        payload = json.dumps(state, ensure_ascii=False)
        try:
            self._redis.setex(self._key(state["session_id"]), self._ttl_seconds, payload)
        except Exception as exc:
            logger.warning("Redis session save failed: %s", exc)

    def clear(self, session_id: str) -> None:
        try:
            self._redis.delete(self._key(session_id))
        except Exception as exc:
            logger.warning("Redis session clear failed: %s", exc)

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}ai_approval:session:{session_id}"


def build_session_state_service() -> SessionStateService:
    """根据环境变量创建会话存储。"""
    backend = os.getenv("AI_APPROVAL_SESSION_BACKEND", "redis").strip().lower()
    if backend == "memory":
        return InMemorySessionStateService()
    host = os.getenv("REDIS_HOST", "").strip()
    if not host:
        return InMemorySessionStateService()
    try:
        import redis

        client = redis.Redis(
            host=host,
            port=int(os.getenv("REDIS_PORT", "6379")),
            password=os.getenv("REDIS_PASSWORD") or None,
            db=int(os.getenv("REDIS_DB", "0")),
            decode_responses=True,
            socket_connect_timeout=float(os.getenv("REDIS_CONNECT_TIMEOUT", "1.5")),
            socket_timeout=float(os.getenv("REDIS_SOCKET_TIMEOUT", "1.5")),
        )
        client.ping()
    except Exception as exc:
        logger.warning("Redis session backend unavailable, using memory: %s", exc)
        return InMemorySessionStateService()
    return RedisSessionStateService(
        redis_client=client,
        key_prefix=os.getenv("REDIS_PREFIX", ""),
        ttl_seconds=_session_ttl_from_env(),
    )


def _session_ttl_from_env() -> int:
    raw_value = os.getenv("AI_APPROVAL_SESSION_TTL_SECONDS", "")
    if not raw_value:
        return DEFAULT_SESSION_TTL_SECONDS
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_SESSION_TTL_SECONDS


session_state_service = build_session_state_service()

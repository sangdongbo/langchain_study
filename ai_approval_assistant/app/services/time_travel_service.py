from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import logging
import os
from typing import Any
from uuid import uuid4

from app.graph.state import ApprovalState
from app.schemas.time_travel import (
    TimeTravelCheckpointDetail,
    TimeTravelCheckpointSummary,
)

DEFAULT_MAX_CHECKPOINTS_PER_SESSION = 50
DEFAULT_CHECKPOINT_TTL_SECONDS = 7200
SECRET_KEYS = {"authorization", "token", "access_token", "refresh_token", "password"}
logger = logging.getLogger("ai_approval_assistant.time_travel")


@dataclass(frozen=True)
class TimeTravelCheckpoint:
    checkpoint_id: str
    session_id: str
    user_id: str
    turn_index: int
    created_at: str
    message: str
    status: str
    intent: str | None
    trace: list[str]
    summary: str
    state: ApprovalState


class TimeTravelService:
    """In-memory checkpoints for learning LangGraph-style time travel."""

    def __init__(self, max_checkpoints_per_session: int = DEFAULT_MAX_CHECKPOINTS_PER_SESSION):
        self._max_checkpoints_per_session = max(1, max_checkpoints_per_session)
        self._checkpoints: dict[str, list[TimeTravelCheckpoint]] = {}

    def record(
        self,
        state: ApprovalState,
        *,
        user_message: str | None = None,
    ) -> TimeTravelCheckpoint:
        session_id = state["session_id"]
        checkpoints = self._checkpoints.setdefault(session_id, [])
        checkpoint = TimeTravelCheckpoint(
            checkpoint_id=f"ckpt_{uuid4().hex}",
            session_id=session_id,
            user_id=state["user_id"],
            turn_index=len(checkpoints) + 1,
            created_at=datetime.now(UTC).isoformat(),
            message=(user_message if user_message is not None else state.get("user_message", "")),
            status=state.get("status", "idle"),
            intent=state.get("intent"),
            trace=list(state.get("trace", [])),
            summary=self._summary_for_state(state),
            state=deepcopy(state),
        )
        checkpoints.append(checkpoint)
        if len(checkpoints) > self._max_checkpoints_per_session:
            del checkpoints[: len(checkpoints) - self._max_checkpoints_per_session]
            self._renumber_turns(session_id)
        return checkpoint

    def list(self, session_id: str, user_id: str) -> list[TimeTravelCheckpointSummary]:
        return [
            self._to_summary(checkpoint)
            for checkpoint in self._checkpoints.get(session_id, [])
            if checkpoint.user_id == user_id
        ]

    def get(
        self,
        session_id: str,
        checkpoint_id: str,
        user_id: str,
    ) -> TimeTravelCheckpointDetail | None:
        checkpoint = self._find(session_id, checkpoint_id, user_id)
        if checkpoint is None:
            return None
        return TimeTravelCheckpointDetail(
            **self._to_summary(checkpoint).model_dump(),
            state=self._public_state(checkpoint.state),
        )

    def restore(
        self,
        session_id: str,
        checkpoint_id: str,
        user_id: str,
    ) -> ApprovalState | None:
        checkpoint = self._find(session_id, checkpoint_id, user_id)
        if checkpoint is None:
            return None
        return deepcopy(checkpoint.state)

    def fork(
        self,
        session_id: str,
        checkpoint_id: str,
        user_id: str,
        new_session_id: str,
    ) -> ApprovalState | None:
        state = self.restore(session_id, checkpoint_id, user_id)
        if state is None:
            return None
        state["session_id"] = new_session_id
        state["user_id"] = user_id
        return state

    def public_state(self, state: ApprovalState) -> dict[str, Any]:
        return self._public_state(state)

    def clear(self, session_id: str) -> None:
        self._checkpoints.pop(session_id, None)

    def _find(
        self,
        session_id: str,
        checkpoint_id: str,
        user_id: str,
    ) -> TimeTravelCheckpoint | None:
        return next(
            (
                checkpoint
                for checkpoint in self._checkpoints.get(session_id, [])
                if checkpoint.checkpoint_id == checkpoint_id
                and checkpoint.user_id == user_id
            ),
            None,
        )

    def _to_summary(
        self,
        checkpoint: TimeTravelCheckpoint,
    ) -> TimeTravelCheckpointSummary:
        return TimeTravelCheckpointSummary(
            checkpoint_id=checkpoint.checkpoint_id,
            session_id=checkpoint.session_id,
            user_id=checkpoint.user_id,
            turn_index=checkpoint.turn_index,
            created_at=checkpoint.created_at,
            message=checkpoint.message,
            status=checkpoint.status,
            intent=checkpoint.intent,
            trace=checkpoint.trace,
            summary=checkpoint.summary,
        )

    def _summary_for_state(self, state: ApprovalState) -> str:
        status = state.get("status", "idle")
        trace_tail = " -> ".join(state.get("trace", [])[-3:])
        if trace_tail:
            return f"{status} · {trace_tail}"
        return status

    def _public_state(self, state: ApprovalState) -> dict[str, Any]:
        return _redact_secrets(deepcopy(dict(state)))

    def _renumber_turns(self, session_id: str) -> None:
        checkpoints = self._checkpoints.get(session_id, [])
        self._checkpoints[session_id] = [
            TimeTravelCheckpoint(
                checkpoint_id=checkpoint.checkpoint_id,
                session_id=checkpoint.session_id,
                user_id=checkpoint.user_id,
                turn_index=index,
                created_at=checkpoint.created_at,
                message=checkpoint.message,
                status=checkpoint.status,
                intent=checkpoint.intent,
                trace=checkpoint.trace,
                summary=checkpoint.summary,
                state=checkpoint.state,
            )
            for index, checkpoint in enumerate(checkpoints, start=1)
        ]


class RedisTimeTravelService(TimeTravelService):
    """Redis-backed checkpoints with the same API as the in-memory service."""

    def __init__(
        self,
        redis_client: Any,
        key_prefix: str = "",
        ttl_seconds: int = DEFAULT_CHECKPOINT_TTL_SECONDS,
        max_checkpoints_per_session: int = DEFAULT_MAX_CHECKPOINTS_PER_SESSION,
    ) -> None:
        super().__init__(max_checkpoints_per_session=max_checkpoints_per_session)
        self._redis = redis_client
        self._key_prefix = key_prefix or ""
        self._ttl_seconds = max(1, ttl_seconds)

    def record(
        self,
        state: ApprovalState,
        *,
        user_message: str | None = None,
    ) -> TimeTravelCheckpoint:
        session_id = state["session_id"]
        checkpoints = self._load_checkpoints(session_id)
        checkpoint = TimeTravelCheckpoint(
            checkpoint_id=f"ckpt_{uuid4().hex}",
            session_id=session_id,
            user_id=state["user_id"],
            turn_index=len(checkpoints) + 1,
            created_at=datetime.now(UTC).isoformat(),
            message=(user_message if user_message is not None else state.get("user_message", "")),
            status=state.get("status", "idle"),
            intent=state.get("intent"),
            trace=list(state.get("trace", [])),
            summary=self._summary_for_state(state),
            state=deepcopy(state),
        )
        checkpoints.append(checkpoint)
        if len(checkpoints) > self._max_checkpoints_per_session:
            checkpoints = checkpoints[-self._max_checkpoints_per_session :]
            checkpoints = [
                self._with_turn_index(item, index)
                for index, item in enumerate(checkpoints, start=1)
            ]
            checkpoint = checkpoints[-1]
        self._save_checkpoints(session_id, checkpoints)
        return checkpoint

    def list(self, session_id: str, user_id: str) -> list[TimeTravelCheckpointSummary]:
        return [
            self._to_summary(checkpoint)
            for checkpoint in self._load_checkpoints(session_id)
            if checkpoint.user_id == user_id
        ]

    def get(
        self,
        session_id: str,
        checkpoint_id: str,
        user_id: str,
    ) -> TimeTravelCheckpointDetail | None:
        checkpoint = self._find(session_id, checkpoint_id, user_id)
        if checkpoint is None:
            return None
        return TimeTravelCheckpointDetail(
            **self._to_summary(checkpoint).model_dump(),
            state=self._public_state(checkpoint.state),
        )

    def restore(
        self,
        session_id: str,
        checkpoint_id: str,
        user_id: str,
    ) -> ApprovalState | None:
        checkpoint = self._find(session_id, checkpoint_id, user_id)
        if checkpoint is None:
            return None
        return deepcopy(checkpoint.state)

    def clear(self, session_id: str) -> None:
        try:
            self._redis.delete(self._key(session_id))
        except Exception as exc:
            logger.warning("Redis checkpoint clear failed: %s", exc)

    def _find(
        self,
        session_id: str,
        checkpoint_id: str,
        user_id: str,
    ) -> TimeTravelCheckpoint | None:
        return next(
            (
                checkpoint
                for checkpoint in self._load_checkpoints(session_id)
                if checkpoint.checkpoint_id == checkpoint_id
                and checkpoint.user_id == user_id
            ),
            None,
        )

    def _load_checkpoints(self, session_id: str) -> list[TimeTravelCheckpoint]:
        try:
            payload = self._redis.get(self._key(session_id))
        except Exception as exc:
            logger.warning("Redis checkpoint load failed: %s", exc)
            return []
        if payload is None:
            return []
        if isinstance(payload, bytes):
            payload = payload.decode("utf-8")
        try:
            rows = json.loads(str(payload))
        except (TypeError, ValueError) as exc:
            logger.warning("Redis checkpoint payload invalid: %s", exc)
            return []
        if not isinstance(rows, list):
            return []
        checkpoints: list[TimeTravelCheckpoint] = []
        for row in rows:
            if isinstance(row, dict):
                checkpoint = self._checkpoint_from_dict(row)
                if checkpoint is not None:
                    checkpoints.append(checkpoint)
        return checkpoints

    def _save_checkpoints(
        self,
        session_id: str,
        checkpoints: list[TimeTravelCheckpoint],
    ) -> None:
        payload = json.dumps(
            [self._checkpoint_to_dict(checkpoint) for checkpoint in checkpoints],
            ensure_ascii=False,
        )
        try:
            self._redis.set(self._key(session_id), payload, ex=self._ttl_seconds)
        except Exception as exc:
            logger.warning("Redis checkpoint save failed: %s", exc)

    def _checkpoint_to_dict(self, checkpoint: TimeTravelCheckpoint) -> dict[str, Any]:
        return {
            "checkpoint_id": checkpoint.checkpoint_id,
            "session_id": checkpoint.session_id,
            "user_id": checkpoint.user_id,
            "turn_index": checkpoint.turn_index,
            "created_at": checkpoint.created_at,
            "message": checkpoint.message,
            "status": checkpoint.status,
            "intent": checkpoint.intent,
            "trace": checkpoint.trace,
            "summary": checkpoint.summary,
            "state": checkpoint.state,
        }

    def _checkpoint_from_dict(self, row: dict[str, Any]) -> TimeTravelCheckpoint | None:
        state = row.get("state")
        if not isinstance(state, dict):
            return None
        return TimeTravelCheckpoint(
            checkpoint_id=str(row.get("checkpoint_id") or ""),
            session_id=str(row.get("session_id") or state.get("session_id") or ""),
            user_id=str(row.get("user_id") or state.get("user_id") or ""),
            turn_index=int(row.get("turn_index") or 0),
            created_at=str(row.get("created_at") or ""),
            message=str(row.get("message") or ""),
            status=str(row.get("status") or state.get("status") or "idle"),
            intent=row.get("intent") if isinstance(row.get("intent"), str) else None,
            trace=list(row.get("trace") or []),
            summary=str(row.get("summary") or ""),
            state=deepcopy(state),
        )

    def _with_turn_index(
        self,
        checkpoint: TimeTravelCheckpoint,
        turn_index: int,
    ) -> TimeTravelCheckpoint:
        return TimeTravelCheckpoint(
            checkpoint_id=checkpoint.checkpoint_id,
            session_id=checkpoint.session_id,
            user_id=checkpoint.user_id,
            turn_index=turn_index,
            created_at=checkpoint.created_at,
            message=checkpoint.message,
            status=checkpoint.status,
            intent=checkpoint.intent,
            trace=checkpoint.trace,
            summary=checkpoint.summary,
            state=checkpoint.state,
        )

    def _key(self, session_id: str) -> str:
        return f"{self._key_prefix}ai_approval:checkpoints:{session_id}"


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if key.lower() in SECRET_KEYS and item else _redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


def build_time_travel_service() -> TimeTravelService:
    backend = os.getenv("AI_APPROVAL_CHECKPOINT_BACKEND", "redis").strip().lower()
    if backend == "memory":
        return TimeTravelService(_checkpoint_limit_from_env())
    host = os.getenv("REDIS_HOST", "").strip()
    if not host:
        return TimeTravelService(_checkpoint_limit_from_env())
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
            protocol=_redis_protocol_from_env(),
        )
        client.ping()
    except Exception as exc:
        logger.warning("Redis checkpoint backend unavailable, using memory: %s", exc)
        return TimeTravelService(_checkpoint_limit_from_env())
    return RedisTimeTravelService(
        redis_client=client,
        key_prefix=os.getenv("REDIS_PREFIX", ""),
        ttl_seconds=_checkpoint_ttl_from_env(),
        max_checkpoints_per_session=_checkpoint_limit_from_env(),
    )


def _checkpoint_ttl_from_env() -> int:
    raw_value = os.getenv("AI_APPROVAL_CHECKPOINT_TTL_SECONDS", "")
    if not raw_value:
        return DEFAULT_CHECKPOINT_TTL_SECONDS
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_CHECKPOINT_TTL_SECONDS


def _checkpoint_limit_from_env() -> int:
    raw_value = os.getenv("AI_APPROVAL_CHECKPOINT_MAX_PER_SESSION", "")
    if not raw_value:
        return DEFAULT_MAX_CHECKPOINTS_PER_SESSION
    try:
        return max(1, int(raw_value))
    except ValueError:
        return DEFAULT_MAX_CHECKPOINTS_PER_SESSION


def _redis_protocol_from_env() -> int:
    raw_value = os.getenv("REDIS_PROTOCOL", "2")
    try:
        protocol = int(raw_value)
    except ValueError:
        return 2
    if protocol not in {2, 3}:
        return 2
    return protocol


time_travel_service = build_time_travel_service()

from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from app.graph.state import ApprovalState
from app.schemas.time_travel import (
    TimeTravelCheckpointDetail,
    TimeTravelCheckpointSummary,
)

DEFAULT_MAX_CHECKPOINTS_PER_SESSION = 50
SECRET_KEYS = {"authorization", "token", "access_token", "refresh_token", "password"}


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


def _redact_secrets(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***REDACTED***" if key.lower() in SECRET_KEYS and item else _redact_secrets(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_redact_secrets(item) for item in value]
    return value


time_travel_service = TimeTravelService()

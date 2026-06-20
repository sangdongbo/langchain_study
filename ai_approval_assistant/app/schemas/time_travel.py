from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TimeTravelCheckpointSummary(BaseModel):
    """A compact checkpoint row for timeline displays."""

    checkpoint_id: str
    session_id: str
    user_id: str
    turn_index: int
    created_at: str
    message: str = ""
    status: str = "idle"
    intent: str | None = None
    trace: list[str] = Field(default_factory=list)
    summary: str = ""


class TimeTravelCheckpointDetail(TimeTravelCheckpointSummary):
    """A checkpoint with a readable state snapshot."""

    state: dict[str, Any] = Field(default_factory=dict)


class RestoreCheckpointRequest(BaseModel):
    checkpoint_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)


class RestoreCheckpointResponse(BaseModel):
    checkpoint_id: str
    session_id: str
    state: dict[str, Any] = Field(default_factory=dict)


class ForkCheckpointRequest(BaseModel):
    checkpoint_id: str = Field(min_length=1)
    user_id: str = Field(min_length=1)
    new_session_id: str = Field(min_length=1)


class ForkCheckpointResponse(BaseModel):
    checkpoint_id: str
    source_session_id: str
    session_id: str
    state: dict[str, Any] = Field(default_factory=dict)

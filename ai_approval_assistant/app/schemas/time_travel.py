from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class TimeTravelCheckpointSummary(BaseModel):
    """用于时间线展示的精简检查点记录。"""

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
    """包含可读状态快照的检查点。"""

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

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.schemas.time_travel import (
    ForkCheckpointRequest,
    ForkCheckpointResponse,
    RestoreCheckpointRequest,
    RestoreCheckpointResponse,
    TimeTravelCheckpointDetail,
    TimeTravelCheckpointSummary,
)
from app.services.session_state_service import session_state_service
from app.services.time_travel_service import time_travel_service

router = APIRouter(prefix="/api/ai-approval/time-travel", tags=["time-travel"])


@router.get(
    "/{session_id}/checkpoints",
    response_model=list[TimeTravelCheckpointSummary],
)
def list_checkpoints(
    session_id: str,
    user_id: str = Query(min_length=1),
) -> list[TimeTravelCheckpointSummary]:
    """List checkpoints recorded for a chat session."""
    return time_travel_service.list(session_id, user_id)


@router.get(
    "/{session_id}/checkpoints/{checkpoint_id}",
    response_model=TimeTravelCheckpointDetail,
)
def get_checkpoint(
    session_id: str,
    checkpoint_id: str,
    user_id: str = Query(min_length=1),
) -> TimeTravelCheckpointDetail:
    """Read a checkpoint snapshot for inspection."""
    checkpoint = time_travel_service.get(session_id, checkpoint_id, user_id)
    if checkpoint is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    return checkpoint


@router.post(
    "/{session_id}/restore",
    response_model=RestoreCheckpointResponse,
)
def restore_checkpoint(
    session_id: str,
    request: RestoreCheckpointRequest,
) -> RestoreCheckpointResponse:
    """Restore a session to a previous checkpoint."""
    state = time_travel_service.restore(
        session_id,
        request.checkpoint_id,
        request.user_id,
    )
    if state is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    session_state_service.save(state)
    detail = time_travel_service.get(session_id, request.checkpoint_id, request.user_id)
    return RestoreCheckpointResponse(
        checkpoint_id=request.checkpoint_id,
        session_id=session_id,
        state=detail.state if detail else {},
    )


@router.post(
    "/{session_id}/fork",
    response_model=ForkCheckpointResponse,
)
def fork_checkpoint(
    session_id: str,
    request: ForkCheckpointRequest,
) -> ForkCheckpointResponse:
    """Fork a checkpoint into a new session."""
    state = time_travel_service.fork(
        session_id,
        request.checkpoint_id,
        request.user_id,
        request.new_session_id,
    )
    if state is None:
        raise HTTPException(status_code=404, detail="Checkpoint not found")
    session_state_service.save(state)
    return ForkCheckpointResponse(
        checkpoint_id=request.checkpoint_id,
        source_session_id=session_id,
        session_id=request.new_session_id,
        state=time_travel_service.public_state(state),
    )

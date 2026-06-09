from __future__ import annotations

from copy import deepcopy

from ai_approval_assistant.app.graph.state import ApprovalState, initial_state


class InMemorySessionStateService:
    """Temporary session store. Replace with Redis for deployment."""

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


session_state_service = InMemorySessionStateService()

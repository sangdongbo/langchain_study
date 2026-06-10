from __future__ import annotations
from copy import deepcopy
from ai_approval_assistant.app.graph.state import ApprovalState, initial_state


class InMemorySessionStateService:
    """临时会话存储；部署时建议替换为 Redis。"""

    def __init__(self) -> None:
        """初始化内存会话字典。"""
        self._states: dict[str, ApprovalState] = {}

    def load(self, session_id: str, user_id: str) -> ApprovalState:
        """加载会话状态；不存在时创建新状态。"""
        state = self._states.get(session_id)
        if state is None:
            return initial_state(session_id=session_id, user_id=user_id)
        loaded = deepcopy(state)
        loaded["user_id"] = user_id
        return loaded

    def save(self, state: ApprovalState) -> None:
        """保存会话的最新状态快照。"""
        self._states[state["session_id"]] = deepcopy(state)

    def clear(self, session_id: str) -> None:
        """从内存存储中移除指定会话。"""
        self._states.pop(session_id, None)


session_state_service = InMemorySessionStateService()

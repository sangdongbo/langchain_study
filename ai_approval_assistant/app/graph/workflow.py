from __future__ import annotations

from app.agents import approval_agent as _approval_agent
from app.agents.approval_agent import *  # noqa: F403
from app.agents.approval_agent import create_workflow, run_chat_turn


class _WorkflowObjectProxy:
    """让旧 monkeypatch 路径继续代理到 approval_agent 模块。"""

    def __init__(self, object_name: str) -> None:
        object.__setattr__(self, "_object_name", object_name)

    def _target(self):
        return getattr(_approval_agent, object.__getattribute__(self, "_object_name"))

    def __getattr__(self, name):
        return getattr(self._target(), name)

    def __setattr__(self, name, value):
        setattr(self._target(), name, value)


crm_approval_service = _WorkflowObjectProxy("crm_approval_service")
model_service = _WorkflowObjectProxy("model_service")

__all__ = [
    "create_workflow",
    "run_chat_turn",
]

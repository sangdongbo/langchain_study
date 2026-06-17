from __future__ import annotations

import logging

from app.graph.state import ApprovalAgentState
from app.schemas.approval import UserContext
from app.services.user_service import user_service

logger = logging.getLogger("ai_approval_assistant.user")


def load_user_profiles(state: ApprovalAgentState) -> ApprovalAgentState:
    """加载当前用户和直属上级信息，返回可合并到 AgentState 的更新。"""
    trace = [*state.get("trace", []), "user_profile_agent"]
    if not state.get("uid") or not state.get("authorization"):
        return {
            **state,
            "user_profile": state.get("user_profile"),
            "superior_profile": state.get("superior_profile"),
            "trace": trace,
        }
    user = UserContext(
        user_id=state["user_id"],
        name=f"User {state['user_id']}",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid=state.get("uid"),
        authorization=state.get("authorization"),
    )
    try:
        user_profile = user_service.get_userinfo(user)
        superior_profile = user_service.get_superior_info(user)
    except Exception as exc:
        logger.warning("Load user profiles failed: %s", exc)
        return {
            **state,
            "user_profile": state.get("user_profile"),
            "superior_profile": state.get("superior_profile"),
            "trace": trace,
        }
    return {
        **state,
        "user_profile": user_profile or None,
        "superior_profile": superior_profile or None,
        "trace": trace,
    }

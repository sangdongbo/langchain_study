from __future__ import annotations

import logging

from app.graph.state import ApprovalAgentState
from app.schemas.approval import UserContext
from app.services.user_service import user_service

logger = logging.getLogger("ai_approval_assistant.user")


def load_user_profiles(state: ApprovalAgentState) -> ApprovalAgentState:
    """加载当前用户和直属上级信息，返回可合并到 AgentState 的更新。"""
    trace = [*state.get("trace", []), "user_profile_agent"]
    tool_calls = list(state.get("_tool_calls", []))
    if not state.get("uid") or not state.get("authorization"):
        return {
            **state,
            "user_profile": state.get("user_profile"),
            "superior_profile": state.get("superior_profile"),
            "trace": trace,
            "_tool_calls": tool_calls,
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
    except Exception as exc:
        logger.warning("Load user profiles failed: %s", exc)
        tool_calls.append(
            {
                "name": "get_current_user_info",
                "status": "error",
                "error": str(exc),
            }
        )
        return {
            **state,
            "user_profile": state.get("user_profile"),
            "superior_profile": state.get("superior_profile"),
            "trace": trace,
            "_tool_calls": tool_calls,
        }
    tool_calls.append(
        {
            "name": "get_current_user_info",
            "status": "success",
            "result": user_profile,
        }
    )
    try:
        superior_id = str((user_profile or {}).get("superior_id") or "").strip()
        if not superior_id or superior_id == "0":
            superior_profile = {}
        else:
            superior_profile = user_service.get_user_detail(user, superior_id)
    except Exception as exc:
        logger.warning("Load superior profile failed: %s", exc)
        tool_calls.append(
            {
                "name": "get_user_superior_info",
                "status": "error",
                "error": str(exc),
            }
        )
        superior_profile = state.get("superior_profile")
    else:
        tool_calls.append(
            {
                "name": "get_user_superior_info",
                "status": "success",
                "result": superior_profile,
            }
        )
    return {
        **state,
        "user_profile": user_profile or None,
        "superior_profile": superior_profile or None,
        "trace": trace,
        "_tool_calls": tool_calls,
    }

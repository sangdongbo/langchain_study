from __future__ import annotations

from functools import lru_cache

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from app.agents import approval_agent as _approval_agent
from app.agents.approval_agent import *  # noqa: F403
from app.agents.approval_agent import (
    general_chat_node,
    intent_router_node,
    memory_agent_node,
    user_info_agent_node,
    user_profile_agent_node,
)
from app.agents.daily_report_create_agent import daily_report_create_agent_node
from app.graph.approval_workflow import create_approval_creation_workflow
from app.graph.daily_report_workflow import create_daily_report_workflow
from app.graph.state import ApprovalState
from app.schemas.chat import ChatRequest, ChatResponse


def create_workflow(*, with_checkpointer: bool = True):
    """创建并编译顶层多 Agent 编排图。

    workflow.py 是主图入口；审批、日报等业务细节放到各自 *_workflow.py 子图。
    """
    builder = StateGraph(ApprovalState)
    builder.add_node("memory_agent", memory_agent_node)
    builder.add_node("user_profile_agent", user_profile_agent_node)
    builder.add_node("intent_router", intent_router_node)
    builder.add_node("user_info_agent", user_info_agent_node)
    builder.add_node("approval_creation_agent", create_approval_creation_workflow())
    builder.add_node("daily_report_agent", create_daily_report_workflow())
    builder.add_node("daily_report_create_agent", daily_report_create_agent_node)
    builder.add_node("general_chat", general_chat_node)
    builder.add_edge(START, "memory_agent")
    builder.add_edge("memory_agent", "intent_router")
    builder.add_conditional_edges(
        "intent_router",
        _route,
        {
            "approval_creation_agent": "approval_creation_agent",
            # 真实审批发起需要当前用户/上级上下文，先走 user_profile_agent 再进审批子图。
            "approval_creation_with_profile": "user_profile_agent",
            "user_info_agent": "user_profile_agent",
            "daily_report_agent": "daily_report_agent",
            "daily_report_create_agent": "daily_report_create_agent",
            "general_chat": "general_chat",
        },
    )
    builder.add_conditional_edges(
        "user_profile_agent",
        _route,
        {
            "approval_creation_with_profile": "approval_creation_agent",
            "user_info_agent": "user_info_agent",
            "end": END,
        },
    )
    builder.add_edge("approval_creation_agent", END)
    builder.add_edge("daily_report_agent", END)
    builder.add_edge("daily_report_create_agent", END)
    builder.add_edge("user_info_agent", END)
    builder.add_edge("general_chat", END)
    # MemorySaver 支持 LangGraph 原生 interrupt/resume；ChatApplicationService
    # 通过 thread_id 让同一个 session 恢复到上次暂停的位置。
    # LangGraph Studio/API 自带持久化能力，导出给 Studio 的图不能携带自定义 checkpointer。
    if not with_checkpointer:
        return builder.compile()
    return builder.compile(checkpointer=MemorySaver())


@lru_cache(maxsize=1)
def get_workflow():
    """返回带 checkpointer 的生产主图实例，支持 interrupt resume。"""
    # 生产环境复用同一个 compiled graph，避免每轮请求重建 checkpointer。
    return create_workflow()


def _route(state: ApprovalState) -> str:
    """从状态中读取下一步图路由。"""
    return state.get("_route", "end")


def run_chat_turn(request: ChatRequest) -> ChatResponse:
    """兼容旧导入路径；新的 API 层应使用 chat_application_service。"""
    from app.services.chat_application_service import chat_application_service

    return chat_application_service.run_turn(request)


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
    "get_workflow",
    "create_approval_creation_workflow",
    "run_chat_turn",
]

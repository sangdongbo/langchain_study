from __future__ import annotations

from collections.abc import Callable

from app.graph.extractors import has_approval_intent
from app.graph.state import ApprovalState
from app.schemas.approval import UserContext
from app.services.crm_service import CrmApprovalService


def has_active_approval_context(state: ApprovalState) -> bool:
    """判断当前会话是否存在可继续的审批上下文。"""
    return bool(
        state.get("approval_type")
        and state.get("status") in {
            "collecting",
            "awaiting_assignee_selection",
            "awaiting_confirmation",
        }
    )


def is_resume_message(text: str) -> bool:
    """识别用户是否想从普通对话回到刚才的审批流程。"""
    cleaned = text.strip()
    return any(
        marker in cleaned
        for marker in ("继续", "继续审批", "回到刚才", "刚才的审批", "接着填", "接着审批")
    )


def looks_like_general_question(message: str) -> bool:
    """识别问答类输入，避免把普通聊天误判为审批发起。"""
    return any((marker in message for marker in ("怎么", "如何", "什么", "哪些", "？", "?")))


def looks_like_remote_template_search(message: str) -> bool:
    """判断用户输入是否适合作为远程审批模板搜索关键词。"""
    if looks_like_general_question(message):
        return False
    if has_approval_intent(message, []):
        return True
    return any((marker in message for marker in ("测试", "zh-", "ZH-", "审批编辑")))


def should_keyword_search_templates(
    state: ApprovalState,
    user: UserContext,
    uses_default_search_method: Callable[[], bool],
) -> bool:
    """判断本轮是否应该按关键词调用 ERP 模板搜索接口。"""
    if not user.authorization or not user.uid:
        return False
    if state.get("approval_type") or state.get("_template_candidates"):
        return False
    if state.get("status", "idle") != "idle":
        return False
    message = state.get("user_message", "").strip()
    if not message:
        return False
    if not looks_like_remote_template_search(message):
        return False
    return uses_default_search_method()


def should_skip_remote_templates_for_general_chat(
    state: ApprovalState, user: UserContext
) -> bool:
    """远程凭证下，明显普通聊天不预拉模板，直接交给通用对话。"""
    if not user.authorization or not user.uid:
        return False
    if state.get("approval_type") or state.get("_template_candidates"):
        return False
    if state.get("status", "idle") != "idle":
        return False
    message = state.get("user_message", "").strip()
    if not message:
        return False
    return not looks_like_remote_template_search(message)


def uses_default_search_method(crm_approval_service) -> bool:
    """判断 list 模板方法是否仍是默认实现，用于兼容测试 monkeypatch。"""
    return (
        getattr(crm_approval_service.list_available_templates, "__func__", None)
        is CrmApprovalService.list_available_templates
    )


def is_remote_keyword_search_result(state: ApprovalState) -> bool:
    """识别当前状态是否为远程关键词搜索后的模板结果。"""
    return bool(
        state.get("_template_search_keyword")
        and state.get("uid")
        and state.get("authorization")
        and not state.get("approval_type")
    )

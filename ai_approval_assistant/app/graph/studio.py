from __future__ import annotations

from app.graph.state import ApprovalState, initial_state
from app.graph.approval_workflow import create_workflow


graph = create_workflow()


def _example_state(session_id: str, user_id: str, message: str) -> ApprovalState:
    state = initial_state(session_id=session_id, user_id=user_id)
    state["user_message"] = message
    return state


STUDIO_EXAMPLES: dict[str, ApprovalState] = {
    "new_purchase": _example_state(
        "studio-new-purchase",
        "U001",
        "我要申请采购笔记本电脑",
    ),
    "new_expense": _example_state(
        "studio-new-expense",
        "U001",
        "我要报销餐饮费 2000 元，客户招待，发票已提供",
    ),
    "resume_collecting": {
        **_example_state("studio-resume-collecting", "U001", "继续审批"),
        "status": "collecting",
        "approval_type": "purchase",
        "collected_slots": {"item": "笔记本电脑"},
        "awaiting_field": "数量",
    },
}

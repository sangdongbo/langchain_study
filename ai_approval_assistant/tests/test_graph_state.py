from __future__ import annotations

from langgraph.prebuilt.chat_agent_executor import AgentState

from app.graph.state import ApprovalAgentState, ApprovalState, initial_state


def test_approval_agent_state_extends_langgraph_agent_state() -> None:
    assert AgentState in ApprovalAgentState.__orig_bases__
    assert "messages" in ApprovalAgentState.__annotations__
    assert "remaining_steps" in ApprovalAgentState.__annotations__
    assert ApprovalState is ApprovalAgentState


def test_initial_state_contains_agent_state_and_approval_fields() -> None:
    state = initial_state("S001", "U001")

    assert state["messages"] == []
    assert state["remaining_steps"] == 20
    assert state["session_id"] == "S001"
    assert state["user_id"] == "U001"
    assert state["user_profile"] is None
    assert state["superior_profile"] is None
    assert state["status"] == "idle"
    assert state["approval_nodes"] == []

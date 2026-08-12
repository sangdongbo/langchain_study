from app.agents.approval.responses import to_chat_response
from app.graph.state import initial_state


def test_chat_response_exposes_daily_report_agent_identity() -> None:
    state = initial_state("S-daily-response", "863")
    state.update(
        {
            "intent": "daily_report",
            "daily_report_agent": "daily_report_agentic_workflow_demo",
            "daily_report_mode": "agentic_workflow_demo",
            "status": "awaiting_daily_report_confirmation",
            "assistant_message": "请确认提交。",
        }
    )

    response = to_chat_response(state, crm_approval_service=None)

    assert response.daily_report_agent == "daily_report_agentic_workflow_demo"
    assert response.daily_report_mode == "agentic_workflow_demo"
    assert response.model_dump()["daily_report_agent"] == (
        "daily_report_agentic_workflow_demo"
    )

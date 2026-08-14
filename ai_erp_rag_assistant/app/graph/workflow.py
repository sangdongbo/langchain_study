from __future__ import annotations

from typing import Any

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, StateGraph

from ai_erp_rag_assistant.app.graph.state import ErpRagState
from ai_erp_rag_assistant.app.services.model_service import model_service
from ai_erp_rag_assistant.app.tools.erp_tools import (
    get_current_user,
    get_approval_template,
    query_approval_status,
    submit_approval,
)
from ai_erp_rag_assistant.app.tools.rag_tools import search_knowledge


def _record(state: ErpRagState, tool: str, **data: Any) -> list[dict[str, Any]]:
    calls = list(state.get("tool_calls", []))
    calls.append({"tool": tool, **data})
    return calls


def agent_planner(state: ErpRagState) -> ErpRagState:
    context = {
        "pending_question": state.get("pending_question", ""),
        "pending_preview": state.get("preview", {}),
        "collected_fields": state.get("fields", {}),
        "confirm_requested": state.get("confirm"),
    }
    plan = model_service.plan(state["user_message"], context=context)
    # A pending approval is part of the conversation state. If the user says
    # “确认/提交” without restating intent, keep the workflow route.
    if state.get("preview") and (state.get("confirm") is True or plan.decision == "confirm"):
        plan.route = "approval_workflow"
    if plan.decision == "confirm":
        state["confirm"] = True
    return {
        "route": plan.route,
        "plan": plan.model_dump(),
        "fields": {**state.get("fields", {}), **plan.fields},
        "confirm": state.get("confirm"),
        "tool_calls": _record(state, "llm.agent_planner", plan=plan.model_dump()),
    }


def load_erp_context(state: ErpRagState) -> ErpRagState:
    user = get_current_user(
        state["user_id"],
        uid=state.get("uid", ""),
        authorization=state.get("authorization", ""),
        company_id=state.get("company_id", ""),
        department=state.get("department", ""),
    )
    return {
        "user_context": user,
        "tool_calls": _record(
            state,
            "erp.get_current_user",
            mode=user.get("erp_mode"),
            company_id=user.get("company_id"),
            department=user.get("department"),
        ),
    }


def retrieve_rag(state: ErpRagState) -> ErpRagState:
    user = state["user_context"]
    evidence = search_knowledge(
        state.get("plan", {}).get("query") or state["user_message"],
        company_id=str(user.get("company_id", "")),
        department=str(user.get("department", "")),
    )
    return {
        "evidence": evidence,
        "tool_calls": _record(
            state,
            "rag.milvus.search",
            collection="erp_knowledge_chunks",
            result_count=len(evidence),
        ),
    }


def query_erp_status_node(state: ErpRagState) -> ErpRagState:
    data = query_approval_status(state["user_id"], user=state.get("user_context", {}))
    return {
        "erp_data": data,
        "tool_calls": _record(state, "erp.approval_status", mode=data.get("erp_mode"), result_keys=list(data.keys())),
    }


def load_approval_template(state: ErpRagState) -> ErpRagState:
    user = state["user_context"]
    approval_type = state.get("plan", {}).get("approval_type") or "请假"
    template = get_approval_template(approval_type, str(user.get("company_id", "")), user=user)
    template["requested_approval_type"] = approval_type
    fields = dict(state.get("fields", {}))
    field_names = {str(item.get("name")) for item in template.get("fields", []) if isinstance(item, dict)}
    # Normalize planner concepts into whichever dynamic ERP field names exist.
    # This is schema-driven and works for remote templates with different fields.
    if "leave_type" in field_names and not fields.get("leave_type") and approval_type:
        fields["leave_type"] = approval_type
    if "reason" in field_names and not fields.get("reason") and state.get("plan", {}).get("reason"):
        fields["reason"] = state["plan"]["reason"]
    return {
        "template": template,
        "fields": fields,
        "tool_calls": _record(
            state,
            "erp.approval_template",
            mode=template.get("erp_mode"),
            template_id=template.get("template_id"),
            field_count=len(template.get("fields", [])),
        ),
    }


def validate_and_preview(state: ErpRagState) -> ErpRagState:
    if state.get("plan", {}).get("decision") == "cancel":
        return {
            "preview": {},
            "pending_question": "",
            "assistant_message": "已取消当前审批草稿。",
            "fields": {},
            "tool_calls": _record(state, "erp.cancel_draft", cancelled=True),
        }
    template = state.get("template", {})
    fields = state.get("fields", {})
    missing = [
        str(field.get("label") or field.get("name"))
        for field in template.get("fields", [])
        if field.get("required") and not fields.get(field.get("name"))
    ]
    if missing:
        question = "请补充以下必填信息：" + "、".join(missing)
        return {
            "pending_question": question,
            "assistant_message": question,
            "preview": {},
            "tool_calls": _record(state, "erp.validate_fields", valid=False, missing=missing),
        }
    preview = {
        "template_code": template.get("template_code"),
        "template_id": template.get("template_id"),
        "title": template.get("title") or "请假审批",
        "fields": fields,
        "requires_confirmation": True,
    }
    return {
        "preview": preview,
        "pending_question": "",
        "assistant_message": "字段已补齐，已生成审批预览。请回复“确认提交”或“取消”。",
        "tool_calls": _record(state, "erp.validate_fields", valid=True, field_count=len(fields)),
    }


def submit_if_confirmed(state: ErpRagState) -> ErpRagState:
    if state.get("confirm") is not True or not state.get("preview"):
        return state
    result = submit_approval(state["preview"], user=state.get("user_context", {}))
    return {
        "erp_data": result,
        "assistant_message": f"已完成提交：{result.get('approval_id') or result.get('message') or '请查看 ERP 返回结果'}。",
        "preview": {},
        "tool_calls": _record(state, "erp.approval_submit", mode=result.get("erp_mode"), result=result),
    }


def answer_with_llm(state: ErpRagState) -> ErpRagState:
    route = state.get("route", "general_chat")
    if route == "approval_workflow":
        return state
    message = model_service.answer(
        state["user_message"],
        route=route,
        evidence=state.get("evidence"),
        erp_data=state.get("erp_data"),
    )
    return {
        "assistant_message": message,
        "tool_calls": _record(state, "llm.answer", route=route),
    }


def handle_error(state: ErpRagState, error: Exception) -> ErpRagState:
    message = f"执行失败：{error}"
    return {
        "assistant_message": message,
        "errors": [*state.get("errors", []), str(error)],
        "tool_calls": _record(state, "system.error", error=str(error)),
    }


def create_workflow():
    builder = StateGraph(ErpRagState)
    builder.add_node("agent_planner", agent_planner)
    builder.add_node("load_erp_context", load_erp_context)
    builder.add_node("retrieve_rag", retrieve_rag)
    builder.add_node("query_erp_status", query_erp_status_node)
    builder.add_node("load_approval_template", load_approval_template)
    builder.add_node("validate_and_preview", validate_and_preview)
    builder.add_node("submit_if_confirmed", submit_if_confirmed)
    builder.add_node("answer_with_llm", answer_with_llm)
    builder.add_edge(START, "agent_planner")
    builder.add_conditional_edges(
        "agent_planner",
        lambda state: state["route"],
        {
            "knowledge": "load_erp_context",
            "erp_status": "load_erp_context",
            "approval_workflow": "load_erp_context",
            "general_chat": "answer_with_llm",
        },
    )
    builder.add_conditional_edges(
        "load_erp_context",
        lambda state: state["route"],
        {"knowledge": "retrieve_rag", "erp_status": "query_erp_status", "approval_workflow": "load_approval_template"},
    )
    builder.add_edge("retrieve_rag", "answer_with_llm")
    builder.add_edge("query_erp_status", "answer_with_llm")
    builder.add_edge("load_approval_template", "validate_and_preview")
    builder.add_conditional_edges(
        "validate_and_preview",
        lambda state: "submit" if state.get("confirm") is True and state.get("preview") else "end",
        {"submit": "submit_if_confirmed", "end": END},
    )
    builder.add_edge("submit_if_confirmed", END)
    builder.add_edge("answer_with_llm", END)
    return builder.compile(checkpointer=MemorySaver())

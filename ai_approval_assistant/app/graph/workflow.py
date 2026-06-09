from __future__ import annotations

import hashlib
import json

from langgraph.graph import END, START, StateGraph

from ai_approval_assistant.app.graph.extractors import (
    classify_approval_type,
    extract_slots,
    is_cancel_message,
    is_confirm_message,
    is_switch_message,
)
from ai_approval_assistant.app.graph.state import ApprovalState, initial_state
from ai_approval_assistant.app.schemas.approval import ApprovalTemplate, UserContext
from ai_approval_assistant.app.schemas.chat import (
    ApprovalPreview,
    ChatRequest,
    ChatResponse,
    PreviewField,
)
from ai_approval_assistant.app.services.crm_service import crm_approval_service
from ai_approval_assistant.app.services.model_service import model_service
from ai_approval_assistant.app.services.session_state_service import session_state_service
from ai_approval_assistant.app.services.template_candidate_service import select_template_candidates


MAX_REVIEW_COUNT = 2


def run_chat_turn(request: ChatRequest) -> ChatResponse:
    state = session_state_service.load(request.session_id, request.user_id)
    state["session_id"] = request.session_id
    state["user_id"] = request.user_id
    state["user_message"] = request.message.strip()
    state["trace"] = []

    graph = create_workflow()
    result = graph.invoke(state)
    session_state_service.save(result)
    return _to_response(result)


def create_workflow():
    builder = StateGraph(ApprovalState)
    builder.add_node("load_context", load_context_node)
    builder.add_node("classify", classify_node)
    builder.add_node("decision_review", decision_review_node)
    builder.add_node("collect", collect_node)
    builder.add_node("validate", validate_node)
    builder.add_node("preview", preview_node)
    builder.add_node("submit", submit_node)
    builder.add_node("already_submitted", already_submitted_node)
    builder.add_node("cancel", cancel_node)
    builder.add_node("clarify", clarify_node)

    builder.add_edge(START, "load_context")
    builder.add_edge("load_context", "classify")
    builder.add_edge("classify", "decision_review")
    builder.add_conditional_edges(
        "decision_review",
        _route,
        {
            "collect": "collect",
            "submit": "submit",
            "cancel": "cancel",
            "clarify": "clarify",
            "review": "decision_review",
            "already_submitted": "already_submitted",
        },
    )
    builder.add_conditional_edges("collect", _route, {"validate": "validate", "end": END})
    builder.add_conditional_edges("validate", _route, {"preview": "preview", "end": END})
    builder.add_edge("preview", END)
    builder.add_edge("submit", END)
    builder.add_edge("already_submitted", END)
    builder.add_edge("cancel", END)
    builder.add_edge("clarify", END)
    return builder.compile()


def load_context_node(state: ApprovalState) -> ApprovalState:
    trace = [*state.get("trace", []), "load_context"]
    try:
        user = crm_approval_service.get_user_context(state["user_id"])
        templates = crm_approval_service.list_available_templates(user)
    except ValueError as exc:
        return {
            **state,
            "status": "error",
            "assistant_message": str(exc),
            "errors": [str(exc)],
            "trace": trace,
            "_user_context": None,
            "_available_templates": [],
            "_route": "clarify",
        }
    return {
        **state,
        "trace": trace,
        "_user_context": user.model_dump(),
        "_available_templates": [template.model_dump() for template in templates],
    }


def classify_node(state: ApprovalState) -> ApprovalState:
    trace = [*state.get("trace", []), "classify"]
    text = state["user_message"]
    status = state.get("status", "idle")

    if status == "submitted":
        return {**state, "trace": trace, "_route": "already_submitted"}

    if status in {"collecting", "awaiting_confirmation"} and is_cancel_message(text):
        return {**state, "trace": trace, "_route": "cancel"}

    if status == "awaiting_confirmation":
        if is_confirm_message(text):
            return {**state, "confirmed": True, "trace": trace, "_route": "submit"}
        if state.get("approval_type"):
            return {**state, "confirmed": False, "trace": trace, "_route": "collect"}
        return {**state, "trace": trace, "_route": "clarify"}

    available_templates = _templates_from_state(state)
    candidate_templates = select_template_candidates(text, available_templates)
    detected_type = classify_approval_type(text, candidate_templates)
    if not detected_type:
        detected_type = model_service.classify_approval_type(text, candidate_templates)

    if status == "collecting" and state.get("approval_type"):
        if detected_type and detected_type != state.get("approval_type") and is_switch_message(text):
            return {
                **state,
                "approval_type": detected_type,
                "collected_slots": {},
                "awaiting_field": None,
                "confirmed": False,
                "request_id": None,
                "idempotency_key": None,
                "preview": None,
                "trace": trace,
                "_route": "collect",
            }
        return {**state, "trace": trace, "_route": "collect"}

    if not detected_type:
        return {
            **state,
            "assistant_message": _approval_type_clarification(available_templates),
            "trace": trace,
            "_route": "clarify",
        }

    return {
        **state,
        "approval_type": detected_type,
        "status": "collecting",
        "collected_slots": {},
        "awaiting_field": None,
        "confirmed": False,
        "request_id": None,
        "idempotency_key": None,
        "preview": None,
        "trace": trace,
        "_route": "collect",
    }


def decision_review_node(state: ApprovalState) -> ApprovalState:
    """Bounded review before executing a business action.

    This is the place to plug in an LLM-based reviewer later. It must stay
    bounded so unclear routing turns into clarification instead of loops.
    """

    trace = [*state.get("trace", []), "decision_review"]
    review_count = state.get("review_count", 0) + 1
    route = state.get("_route", "clarify")

    if review_count > MAX_REVIEW_COUNT:
        return {
            **state,
            "review_count": 0,
            "assistant_message": "我还不能确定要继续哪一步，请补充说明要办理的审批或要修改的字段。",
            "trace": trace,
            "_route": "clarify",
        }

    if route == "submit":
        if state.get("status") != "awaiting_confirmation" or not state.get("approval_type"):
            return {
                **state,
                "review_count": 0,
                "confirmed": False,
                "assistant_message": "还没有生成可提交的审批预览，请先补全审批信息。",
                "trace": trace,
                "_route": "clarify",
            }
        return {**state, "review_count": 0, "trace": trace, "_route": "submit"}

    if route == "collect" and not state.get("approval_type"):
        templates = _templates_from_state(state)
        return {
            **state,
            "review_count": review_count,
            "assistant_message": _approval_type_clarification(templates),
            "trace": trace,
            "_route": "clarify",
        }

    if route == "collect" and state.get("approval_type"):
        return {**state, "review_count": 0, "trace": trace, "_route": "collect"}

    templates = _templates_from_state(state)
    llm_review = model_service.review_decision(
        route=route,
        status=state.get("status", "idle"),
        approval_type=state.get("approval_type"),
        user_message=state.get("user_message", ""),
        templates=templates,
    )
    reviewed_route = llm_review.get("route")
    if reviewed_route and reviewed_route != route:
        if reviewed_route == "submit":
            return {
                **state,
                "review_count": 0,
                "confirmed": False,
                "assistant_message": "还没有满足提交条件，请先确认审批预览。",
                "trace": trace,
                "_route": "clarify",
            }
        if reviewed_route == "clarify":
            return {
                **state,
                "review_count": 0,
                "assistant_message": _approval_type_clarification(templates),
                "trace": trace,
                "_route": "clarify",
            }
        route = reviewed_route

    return {**state, "review_count": 0, "trace": trace, "_route": route}


def collect_node(state: ApprovalState) -> ApprovalState:
    trace = [*state.get("trace", []), "collect"]
    approval_type = state.get("approval_type")
    if not approval_type:
        return {**state, "trace": trace, "_route": "clarify"}

    user = _user_from_state(state)
    template = crm_approval_service.get_template_detail(approval_type, user)
    slots = dict(state.get("collected_slots", {}))
    rule_slots = extract_slots(template, state["user_message"], state.get("awaiting_field"))
    slots.update(rule_slots)
    llm_slots = model_service.extract_slots(
        template=template,
        user_message=state["user_message"],
        collected_slots=slots,
        awaiting_field=state.get("awaiting_field"),
    )
    for key, value in llm_slots.items():
        slots.setdefault(key, value)

    missing_field = _first_missing_field(template, slots)
    if missing_field:
        question = next(field.question for field in template.fields if field.name == missing_field)
        return {
            **state,
            "status": "collecting",
            "collected_slots": slots,
            "awaiting_field": missing_field,
            "assistant_message": question,
            "preview": None,
            "trace": trace,
            "_route": "end",
        }

    return {
        **state,
        "status": "collecting",
        "collected_slots": slots,
        "awaiting_field": None,
        "trace": trace,
        "_route": "validate",
    }


def validate_node(state: ApprovalState) -> ApprovalState:
    trace = [*state.get("trace", []), "validate"]
    user = _user_from_state(state)
    approval_type = state["approval_type"]
    slots = state.get("collected_slots", {})
    result = crm_approval_service.validate_approval(approval_type, slots, user)

    if not result.valid:
        return {
            **state,
            "status": "collecting",
            "errors": result.errors,
            "field_errors": [error.model_dump() for error in result.field_errors],
            "assistant_message": "\n".join(result.errors),
            "approval_node": result.approval_node,
            "trace": trace,
            "_route": "end",
        }

    return {
        **state,
        "errors": [],
        "field_errors": [],
        "approval_node": result.approval_node,
        "_validation_warnings": result.warnings,
        "trace": trace,
        "_route": "preview",
    }


def preview_node(state: ApprovalState) -> ApprovalState:
    trace = [*state.get("trace", []), "preview"]
    user = _user_from_state(state)
    template = crm_approval_service.get_template_detail(state["approval_type"], user)
    warnings = list(state.get("_validation_warnings", []))
    preview = _build_preview(template, state.get("collected_slots", {}), state.get("approval_node"), warnings)

    lines = [f"请确认是否提交{template.title}：", ""]
    for field in preview.fields:
        lines.append(f"- {field.label}：{field.value}")
    if preview.approval_node:
        lines.append(f"- 预计审批节点：{preview.approval_node}")
    for warning in warnings:
        lines.append(f"- 提示：{warning}")
    lines.extend(["", "回复“确认提交”后我再提交申请。也可以继续说明要修改的字段，或回复“取消”。"])

    return {
        **state,
        "status": "awaiting_confirmation",
        "preview": preview.model_dump(),
        "assistant_message": "\n".join(lines),
        "confirmed": False,
        "trace": trace,
        "_route": "end",
    }


def submit_node(state: ApprovalState) -> ApprovalState:
    trace = [*state.get("trace", []), "submit"]
    if not state.get("confirmed"):
        return {
            **state,
            "assistant_message": "提交前需要你明确回复“确认提交”。",
            "trace": trace,
            "_route": "clarify",
        }

    user = _user_from_state(state)
    idempotency_key = state.get("idempotency_key") or _build_idempotency_key(state)
    result = crm_approval_service.submit_approval(
        state["approval_type"],
        state.get("collected_slots", {}),
        user,
        idempotency_key=idempotency_key,
    )
    return {
        **state,
        "status": "submitted",
        "request_id": result.request_id,
        "approval_node": result.approval_node,
        "idempotency_key": result.idempotency_key,
        "assistant_message": (
            "已提交审批申请。\n\n"
            f"- 申请编号：{result.request_id}\n"
            f"- 当前状态：{result.status}\n"
            f"- 审批节点：{result.approval_node}"
        ),
        "trace": trace,
        "_route": "end",
    }


def already_submitted_node(state: ApprovalState) -> ApprovalState:
    trace = [*state.get("trace", []), "already_submitted"]
    return {
        **state,
        "status": "submitted",
        "assistant_message": (
            "这条审批申请已经提交过。\n\n"
            f"- 申请编号：{state.get('request_id')}\n"
            f"- 审批节点：{state.get('approval_node')}"
        ),
        "trace": trace,
        "_route": "end",
    }


def cancel_node(state: ApprovalState) -> ApprovalState:
    trace = [*state.get("trace", []), "cancel"]
    return {
        **initial_state(state["session_id"], state["user_id"]),
        "status": "cancelled",
        "assistant_message": "已取消本次审批申请，没有提交任何内容。",
        "trace": trace,
        "_route": "end",
    }


def clarify_node(state: ApprovalState) -> ApprovalState:
    trace = [*state.get("trace", []), "clarify"]
    templates = _templates_from_state(state)
    message = state.get("assistant_message") or _approval_type_clarification(templates)
    return {**state, "assistant_message": message, "trace": trace, "_route": "end"}


def _route(state: ApprovalState) -> str:
    return state.get("_route", "end")


def _templates_from_state(state: ApprovalState) -> list[ApprovalTemplate]:
    return [ApprovalTemplate(**item) for item in state.get("_available_templates", [])]


def _user_from_state(state: ApprovalState) -> UserContext:
    user_data = state.get("_user_context")
    if not user_data:
        return crm_approval_service.get_user_context(state["user_id"])
    return UserContext(**user_data)


def _first_missing_field(template: ApprovalTemplate, slots: dict[str, str]) -> str | None:
    for field in template.fields:
        if field.required and not slots.get(field.name):
            return field.name
    return None


def _build_preview(
    template: ApprovalTemplate,
    slots: dict[str, str],
    approval_node: str | None,
    warnings: list[str],
) -> ApprovalPreview:
    return ApprovalPreview(
        approval_type=template.approval_type,
        title=template.title,
        fields=[
            PreviewField(name=field.name, label=field.label, value=slots.get(field.name, ""))
            for field in template.fields
        ],
        approval_node=approval_node,
        warnings=warnings,
    )


def _approval_type_clarification(templates: list[ApprovalTemplate]) -> str:
    if not templates:
        return "当前没有可发起的审批模板。"
    common = [template.title for template in templates if template.is_common][:5]
    categories: dict[str, int] = {}
    for template in templates:
        categories[template.category] = categories.get(template.category, 0) + 1
    category_text = "、".join(f"{name}({count})" for name, count in sorted(categories.items()))
    if common:
        common_text = "、".join(common)
        return f"请告诉我要办理哪类审批。常用审批包括：{common_text}。当前分类：{category_text}。"
    return f"请告诉我要办理哪类审批。当前分类：{category_text}。"


def _to_response(state: ApprovalState) -> ChatResponse:
    preview_data = state.get("preview")
    preview = ApprovalPreview(**preview_data) if preview_data else None
    missing_fields: list[str] = []
    if state.get("awaiting_field"):
        missing_fields.append(state["awaiting_field"])
    return ChatResponse(
        session_id=state["session_id"],
        status=state.get("status", "idle"),
        assistant_message=state.get("assistant_message", ""),
        approval_type=state.get("approval_type"),
        collected_slots=state.get("collected_slots", {}),
        missing_fields=missing_fields,
        awaiting_field=state.get("awaiting_field"),
        preview=preview,
        actions=_actions_for_status(state.get("status", "idle")),
        request_id=state.get("request_id"),
        approval_node=state.get("approval_node"),
        field_errors=state.get("field_errors", []),
        idempotency_key=state.get("idempotency_key"),
        trace=state.get("trace", []),
    )


def _actions_for_status(status: str) -> list[str]:
    if status == "collecting":
        return ["reply", "cancel"]
    if status == "awaiting_confirmation":
        return ["confirm", "modify", "cancel"]
    if status == "submitted":
        return ["query_status"]
    return ["reply"]


def _build_idempotency_key(state: ApprovalState) -> str:
    payload = {
        "session_id": state.get("session_id"),
        "user_id": state.get("user_id"),
        "approval_type": state.get("approval_type"),
        "slots": state.get("collected_slots", {}),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"ai-approval:{digest}"

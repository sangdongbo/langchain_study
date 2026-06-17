from __future__ import annotations
from langgraph.graph import END, START, StateGraph
from app.graph.extractors import (
    classify_approval_type,
    extract_slots,
    has_approval_intent,
    is_cancel_message,
    is_confirm_message,
    is_switch_message,
)
from app.graph.state import ApprovalState, initial_state
from app.agents.approval.assignee import (
    assignee_preview_fields,
    assignee_selection_input,
    assignee_selection_message,
    awaiting_assignee_node_id,
    first_unselected_node,
    select_assignees_from_answer,
    select_assignees_from_message,
)
from app.agents.approval.constants import (
    FIELD_DEPENDENCIES,
    LOCAL_MOCK_APPROVAL_TYPES,
    MAX_REVIEW_COUNT,
)
from app.agents.approval.messages import (
    append_resume_hint,
    approval_type_clarification,
    crm_error_message,
    resume_message,
    template_choice_message,
)
from app.agents.approval.inputs import (
    awaiting_input_for_state,
    awaiting_input_min,
    awaiting_input_type_for_field,
    awaiting_value_schema,
    template_choice_input,
)
from app.agents.approval.responses import (
    actions_for_status,
    build_preview,
    field_labels_for_state,
    labels_from_template,
    to_chat_response,
)
from app.agents.approval.routing import (
    has_active_approval_context,
    is_remote_keyword_search_result,
    is_resume_message,
    looks_like_general_question,
    looks_like_remote_template_search,
    should_keyword_search_templates,
    should_skip_remote_templates_for_general_chat,
    uses_default_search_method,
)
from app.agents.approval.selection import select_template_candidate
from app.agents.approval.submission import build_idempotency_key
from app.agents.approval.state_helpers import (
    clear_dependent_fields,
    form_value_from_slots,
    nodes_from_state,
    slots_from_structured_answer,
    submission_slots,
    template_candidates_from_state,
    template_detail_for_state,
    templates_from_state,
    user_from_state,
)
from app.agents.user_profile_agent import load_user_profiles
from app.schemas.approval import (
    ApprovalAssignee,
    ApprovalNode,
    ApprovalTemplate,
    UserContext,
)
from app.schemas.chat import (
    ApprovalPreview,
    AwaitingInput,
    ChatRequest,
    ChatResponse,
    PreviewField,
)
from app.services.crm_service import crm_approval_service
from app.services.model_service import model_service
from app.services.session_state_service import (
    session_state_service,
)
from app.services.debug_log_service import write_debug_log
from app.services.template_candidate_service import (
    select_template_candidates,
)


def run_chat_turn(request: ChatRequest) -> ChatResponse:
    """将单轮聊天请求放入审批工作流图执行。"""
    write_debug_log("chat.request", request.model_dump())
    state = session_state_service.load(request.session_id, request.user_id)
    if _should_reset_local_state_for_remote_credentials(state, request):
        state = initial_state(request.session_id, request.user_id)
    state["session_id"] = request.session_id
    state["user_id"] = request.user_id
    state["uid"] = request.uid
    state["authorization"] = request.authorization
    state["user_message"] = request.message.strip()
    state["_answer"] = request.answer
    state["trace"] = []
    graph = create_workflow()
    result = graph.invoke(state)
    session_state_service.save(result)
    response = _to_response(result)
    write_debug_log("chat.response", response.model_dump())
    return response


def _should_reset_local_state_for_remote_credentials(
    state: ApprovalState, request: ChatRequest
) -> bool:
    """真实 ERP 凭证进入后，丢弃旧的本地模拟审批会话。"""
    if not request.authorization or not request.uid:
        return False
    approval_type = state.get("approval_type")
    return bool(approval_type and approval_type in LOCAL_MOCK_APPROVAL_TYPES)


def create_workflow():
    """创建并编译 LangGraph 审批工作流。"""
    builder = StateGraph(ApprovalState)
    builder.add_node("load_context", load_context_node)
    builder.add_node("classify", classify_node)
    builder.add_node("decision_review", decision_review_node)
    builder.add_node("collect", collect_node)
    builder.add_node("validate", validate_node)
    builder.add_node("assignee", assignee_node)
    builder.add_node("preview", preview_node)
    builder.add_node("submit", submit_node)
    builder.add_node("already_submitted", already_submitted_node)
    builder.add_node("cancel", cancel_node)
    builder.add_node("clarify", clarify_node)
    builder.add_node("general_chat", general_chat_node)
    builder.add_node("resume", resume_node)
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
            "general_chat": "general_chat",
            "assignee": "assignee",
            "resume": "resume",
        },
    )
    builder.add_conditional_edges(
        "collect", _route, {"validate": "validate", "end": END}
    )
    builder.add_conditional_edges("validate", _route, {"assignee": "assignee", "end": END})
    builder.add_conditional_edges("assignee", _route, {"preview": "preview", "end": END})
    builder.add_edge("preview", END)
    builder.add_edge("submit", END)
    builder.add_edge("already_submitted", END)
    builder.add_edge("cancel", END)
    builder.add_edge("clarify", END)
    builder.add_edge("general_chat", END)
    builder.add_edge("resume", END)
    return builder.compile()


def load_context_node(state: ApprovalState) -> ApprovalState:
    """加载用户上下文和可用审批模板。"""
    state = load_user_profiles(state)
    trace = [*state.get("trace", []), "load_context"]
    try:
        user = crm_approval_service.get_user_context(
            state["user_id"],
            uid=state.get("uid"),
            authorization=state.get("authorization"),
        )
        if state.get("_template_candidates") and not state.get("approval_type"):
            templates = _template_candidates_from_state(state)
            search_keyword = state.get("_template_search_keyword", "")
        elif _should_skip_remote_templates_for_general_chat(state, user):
            templates = []
            search_keyword = ""
        elif _should_keyword_search_templates(state, user):
            search_keyword = state.get("user_message", "").strip()
            templates = crm_approval_service.search_available_templates(
                user, search_keyword
            )
        else:
            search_keyword = ""
            templates = crm_approval_service.list_available_templates(user)
    except ValueError as exc:
        message = _crm_error_message(str(exc))
        return {
            **state,
            "status": "error",
            "assistant_message": message,
            "errors": [message],
            "trace": trace,
            "_user_context": None,
            "_available_templates": [],
            "_template_search_keyword": "",
            "_route": "clarify",
        }
    return {
        **state,
        "trace": trace,
        "_user_context": user.model_dump(),
        "_available_templates": [template.model_dump() for template in templates],
        "_template_search_keyword": search_keyword,
    }


def classify_node(state: ApprovalState) -> ApprovalState:
    """识别用户消息并选择下一步工作流路由。"""
    trace = [*state.get("trace", []), "classify"]
    text = state["user_message"]
    status = state.get("status", "idle")
    if status == "error":
        return {**state, "trace": trace, "_route": "clarify"}
    if status == "submitted":
        return {**state, "trace": trace, "_route": "already_submitted"}
    if status in {
        "collecting",
        "awaiting_confirmation",
        "awaiting_assignee_selection",
    } and is_cancel_message(text):
        return {**state, "trace": trace, "_route": "cancel"}
    if (
        state.get("_template_candidates")
        and not state.get("approval_type")
        and is_cancel_message(text)
    ):
        return {**state, "trace": trace, "_route": "cancel"}
    if _has_active_approval_context(state) and _is_resume_message(text):
        return {**state, "trace": trace, "_route": "resume"}
    if (
        _has_active_approval_context(state)
        and _looks_like_general_question(text)
        and not state.get("_answer")
    ):
        return {**state, "trace": trace, "_route": "general_chat"}
    if status == "awaiting_assignee_selection":
        return {**state, "trace": trace, "_route": "assignee"}
    if status == "awaiting_confirmation":
        if is_confirm_message(text):
            return {**state, "confirmed": True, "trace": trace, "_route": "submit"}
        if state.get("approval_type"):
            return {**state, "confirmed": False, "trace": trace, "_route": "collect"}
        return {**state, "trace": trace, "_route": "clarify"}
    available_templates = _templates_from_state(state)
    if state.get("_template_candidates") and not state.get("approval_type"):
        selected = _select_template_candidate(
            text,
            _template_candidates_from_state(state),
            state.get("_answer"),
        )
        if selected:
            return {
                **state,
                "approval_type": selected.approval_type,
                "status": "collecting",
                "collected_slots": {},
                "collected_values": {},
                "awaiting_field": None,
                "confirmed": False,
                "request_id": None,
                "idempotency_key": None,
                "preview": None,
                "_template_candidates": [],
                "_current_template": None,
                "trace": trace,
                "_route": "collect",
            }
        return {
            **state,
            "assistant_message": _template_choice_message(
                _template_candidates_from_state(state)
            ),
            "trace": trace,
            "_route": "clarify",
        }
    if status == "idle" and _looks_like_general_question(text):
        return {**state, "trace": trace, "_route": "general_chat"}
    if _is_remote_keyword_search_result(state):
        if len(available_templates) == 1:
            return {
                **state,
                "approval_type": available_templates[0].approval_type,
                "status": "collecting",
                "collected_slots": {},
                "collected_values": {},
                "awaiting_field": None,
                "confirmed": False,
                "request_id": None,
                "idempotency_key": None,
                "preview": None,
                "_template_candidates": [],
                "_current_template": None,
                "trace": trace,
                "_route": "collect",
            }
        if len(available_templates) > 1:
            return {
                **state,
                "status": "idle",
                "approval_type": None,
                "_template_candidates": [
                    template.model_dump() for template in available_templates
                ],
                "assistant_message": _template_choice_message(available_templates),
                "trace": trace,
                "_route": "clarify",
            }
        return {
            **state,
            "assistant_message": f"没有找到“{state.get('_template_search_keyword')}”对应的审批模板，请换个关键词再试。",
            "trace": trace,
            "_route": "clarify",
        }
    candidate_templates = select_template_candidates(text, available_templates)
    detected_type = classify_approval_type(text, candidate_templates)
    if not detected_type:
        detected_type = model_service.classify_approval_type(text, candidate_templates)
    if (
        status == "idle"
        and (not detected_type)
        and (not has_approval_intent(text, available_templates))
    ):
        return {**state, "trace": trace, "_route": "general_chat"}
    if status == "collecting" and state.get("approval_type"):
        if (
            detected_type
            and detected_type != state.get("approval_type")
            and is_switch_message(text)
        ):
            return {
                **state,
                "approval_type": detected_type,
                "collected_slots": {},
                "collected_values": {},
                "awaiting_field": None,
                "confirmed": False,
                "request_id": None,
                "idempotency_key": None,
                "preview": None,
                "_current_template": None,
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
        "collected_values": {},
        "awaiting_field": None,
        "confirmed": False,
        "request_id": None,
        "idempotency_key": None,
        "preview": None,
        "_template_candidates": [],
        "_current_template": None,
        "trace": trace,
        "_route": "collect",
    }


def decision_review_node(state: ApprovalState) -> ApprovalState:
    """执行具体业务动作前进行有界复核。

    这里可以接入基于 LLM 的路由复核，但必须保持次数有界；
    不明确的路由应转为澄清，而不是进入循环。
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
        if state.get("status") != "awaiting_confirmation" or not state.get(
            "approval_type"
        ):
            return {
                **state,
                "review_count": 0,
                "confirmed": False,
                "assistant_message": "还没有生成可提交的审批预览，请先补全审批信息。",
                "trace": trace,
                "_route": "clarify",
            }
        return {**state, "review_count": 0, "trace": trace, "_route": "submit"}
    if route == "collect" and (not state.get("approval_type")):
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
    """从当前消息中收集审批必填字段。"""
    trace = [*state.get("trace", []), "collect"]
    approval_type = state.get("approval_type")
    if not approval_type:
        return {**state, "trace": trace, "_route": "clarify"}
    user = _user_from_state(state)
    template = _template_detail_for_state(state, approval_type, user)
    field_labels = {
        **state.get("_field_labels", {}),
        **_labels_from_template(template),
    }
    slots = dict(state.get("collected_slots", {}))
    collected_values = dict(state.get("collected_values", {}))
    answer_slots, answer_values = _slots_from_structured_answer(
        state.get("_answer"),
        state.get("awaiting_field"),
        slots,
    )
    slots.update(answer_slots)
    collected_values.update(answer_values)
    _clear_dependent_fields(slots, collected_values, answer_slots.keys())
    if not answer_slots:
        rule_slots = extract_slots(
            template, state["user_message"], state.get("awaiting_field")
        )
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
        question = next(
            (field.question for field in template.fields if field.name == missing_field)
        )
        return {
            **state,
            "status": "collecting",
            "collected_slots": slots,
            "collected_values": collected_values,
            "awaiting_field": missing_field,
            "_field_labels": field_labels,
            "_current_template": template.model_dump(),
            "assistant_message": question,
            "preview": None,
            "trace": trace,
            "_route": "end",
        }
    return {
        **state,
        "status": "collecting",
        "collected_slots": slots,
        "collected_values": collected_values,
        "awaiting_field": None,
        "_field_labels": field_labels,
        "_current_template": template.model_dump(),
        "trace": trace,
        "_route": "validate",
    }


def validate_node(state: ApprovalState) -> ApprovalState:
    """按 CRM 或模板规则校验已收集字段。"""
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
        "_route": "assignee",
    }


def assignee_node(state: ApprovalState) -> ApprovalState:
    """获取审批节点，并在需要发起人选人时暂停追问。"""
    trace = [*state.get("trace", []), "assignee"]
    user = _user_from_state(state)
    approval_type = state.get("approval_type")
    if not approval_type:
        return {**state, "trace": trace, "_route": "preview"}
    template = _template_detail_for_state(state, approval_type, user)
    if not template.template_id or not approval_type.startswith("remote_"):
        return {**state, "trace": trace, "_route": "preview"}

    nodes = _nodes_from_state(state)
    if not nodes:
        nodes = crm_approval_service.get_approval_nodes(
            approval_set_id=template.template_id,
            form_value=_form_value_from_slots(state.get("collected_slots", {})),
            user=user,
        )
    selected_assignees = dict(state.get("selected_assignees", {}))
    if state.get("status") == "awaiting_assignee_selection":
        node_id = _awaiting_assignee_node_id(state.get("awaiting_field"))
        current_node = next((node for node in nodes if node.node_id == node_id), None)
        if current_node:
            selected = _select_assignees_from_answer(
                current_node,
                state.get("_answer"),
            ) or _select_assignees_from_message(
                current_node,
                state.get("user_message", ""),
            )
            if selected:
                selected_assignees[current_node.node_id] = [assignee.uid for assignee in selected]
            else:
                return {
                    **state,
                    "status": "awaiting_assignee_selection",
                    "approval_nodes": [node.model_dump() for node in nodes],
                    "selected_assignees": selected_assignees,
                    "assistant_message": _assignee_selection_message(current_node),
                    "trace": trace,
                    "_route": "end",
                }
    awaiting_node = _first_unselected_node(nodes, selected_assignees)
    if awaiting_node:
        return {
            **state,
            "status": "awaiting_assignee_selection",
            "approval_nodes": [node.model_dump() for node in nodes],
            "selected_assignees": selected_assignees,
            "awaiting_field": f"assignee:{awaiting_node.node_id}",
            "assistant_message": _assignee_selection_message(awaiting_node),
            "trace": trace,
            "_route": "end",
        }
    return {
        **state,
        "approval_nodes": [node.model_dump() for node in nodes],
        "selected_assignees": selected_assignees,
        "awaiting_field": None,
        "trace": trace,
        "_route": "preview",
    }


def preview_node(state: ApprovalState) -> ApprovalState:
    """生成审批预览并等待用户明确确认。"""
    trace = [*state.get("trace", []), "preview"]
    user = _user_from_state(state)
    template = _template_detail_for_state(state, state["approval_type"], user)
    warnings = list(state.get("_validation_warnings", []))
    preview = _build_preview(
        template, state.get("collected_slots", {}), state.get("approval_node"), warnings
    )
    nodes = _nodes_from_state(state)
    selected_assignees = dict(state.get("selected_assignees", {}))
    preview.fields.extend(_assignee_preview_fields(nodes, selected_assignees))
    lines = [f"请确认是否提交{template.title}：", ""]
    for field in preview.fields:
        lines.append(f"- {field.label}：{field.value}")
    if preview.approval_node:
        lines.append(f"- 预计审批节点：{preview.approval_node}")
    for warning in warnings:
        lines.append(f"- 提示：{warning}")
    lines.extend(
        ["", "回复“确认提交”后我再提交申请。也可以继续说明要修改的字段，或回复“取消”。"]
    )
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
    """在确认守卫通过后提交审批。"""
    trace = [*state.get("trace", []), "submit"]
    if not state.get("confirmed"):
        return {
            **state,
            "assistant_message": "提交前需要你明确回复“确认提交”。",
            "trace": trace,
            "_route": "clarify",
    }
    user = _user_from_state(state)
    template = _template_detail_for_state(state, state["approval_type"], user)
    idempotency_key = state.get("idempotency_key") or _build_idempotency_key(state)
    result = crm_approval_service.submit_approval(
        state["approval_type"],
        _submission_slots(state),
        user,
        idempotency_key=idempotency_key,
        approval_set_id=template.template_id,
        approval_nodes=state.get("approval_nodes", []),
        selected_assignees=state.get("selected_assignees", {}),
    )
    return {
        **state,
        "status": "submitted",
        "request_id": result.request_id,
        "approval_node": result.approval_node,
        "idempotency_key": result.idempotency_key,
        "assistant_message": f"已提交审批申请。\n\n- 申请编号：{result.request_id}\n- 当前状态：{result.status}\n- 审批节点：{result.approval_node}",
        "trace": trace,
        "_route": "end",
    }


def already_submitted_node(state: ApprovalState) -> ApprovalState:
    """对已提交会话返回之前的提交结果。"""
    trace = [*state.get("trace", []), "already_submitted"]
    return {
        **state,
        "status": "submitted",
        "assistant_message": f"这条审批申请已经提交过。\n\n- 申请编号：{state.get('request_id')}\n- 审批节点：{state.get('approval_node')}",
        "trace": trace,
        "_route": "end",
    }


def cancel_node(state: ApprovalState) -> ApprovalState:
    """取消当前审批流程并重置会话状态。"""
    trace = [*state.get("trace", []), "cancel"]
    return {
        **initial_state(state["session_id"], state["user_id"]),
        "status": "cancelled",
        "assistant_message": "已取消本次审批申请，没有提交任何内容。",
        "trace": trace,
        "_route": "end",
    }


def clarify_node(state: ApprovalState) -> ApprovalState:
    """向用户返回当前澄清消息。"""
    trace = [*state.get("trace", []), "clarify"]
    templates = _templates_from_state(state)
    message = state.get("assistant_message") or _approval_type_clarification(templates)
    return {**state, "assistant_message": message, "trace": trace, "_route": "end"}


def general_chat_node(state: ApprovalState) -> ApprovalState:
    """使用通用聊天模型处理非审批消息。"""
    trace = [*state.get("trace", []), "general_chat"]
    answer = model_service.chat(state.get("user_message", ""))
    if _has_active_approval_context(state):
        return {
            **state,
            "assistant_message": _append_resume_hint(answer, state),
            "trace": trace,
            "_route": "end",
        }
    return {
        **state,
        "status": "idle",
        "approval_type": None,
        "collected_slots": {},
        "awaiting_field": None,
        "preview": None,
        "assistant_message": answer,
        "trace": trace,
        "_route": "end",
    }


def resume_node(state: ApprovalState) -> ApprovalState:
    """返回当前审批等待项，帮助用户从闲聊后继续流程。"""
    trace = [*state.get("trace", []), "resume"]
    return {
        **state,
        "assistant_message": _resume_message(state),
        "trace": trace,
        "_route": "end",
    }


def _route(state: ApprovalState) -> str:
    """从状态中读取下一步图路由。"""
    return state.get("_route", "end")


def _templates_from_state(state: ApprovalState) -> list[ApprovalTemplate]:
    """从图状态中反序列化可用模板。"""
    return templates_from_state(state)


def _template_candidates_from_state(state: ApprovalState) -> list[ApprovalTemplate]:
    """从图状态中反序列化等待用户选择的候选模板。"""
    return template_candidates_from_state(state)


def _has_active_approval_context(state: ApprovalState) -> bool:
    """判断当前会话是否有可继续的审批上下文。"""
    return has_active_approval_context(state)


def _is_resume_message(text: str) -> bool:
    """识别用户想回到当前审批流程。"""
    return is_resume_message(text)


def _append_resume_hint(answer: str, state: ApprovalState) -> str:
    """普通问答后附加当前审批等待项，便于用户继续。"""
    return append_resume_hint(answer, state, _current_waiting_label(state))


def _resume_message(state: ApprovalState) -> str:
    """构建继续当前审批的提示。"""
    return resume_message(state, _current_waiting_label(state))


def _current_waiting_label(state: ApprovalState) -> str | None:
    """返回当前等待项的展示名称。"""
    awaiting_field = state.get("awaiting_field")
    if not awaiting_field:
        return None
    if state.get("status") == "awaiting_assignee_selection":
        node_id = _awaiting_assignee_node_id(awaiting_field)
        node = next((item for item in _nodes_from_state(state) if item.node_id == node_id), None)
        return f"{node.node_name}审批人" if node else "办理人/审批人"
    labels = _field_labels_for_state(state, [awaiting_field])
    return labels.get(awaiting_field) or awaiting_field


def _should_keyword_search_templates(
    state: ApprovalState, user: UserContext
) -> bool:
    """判断当前轮是否应按用户关键词直接查 ERP 模板。"""
    return should_keyword_search_templates(state, user, _uses_default_search_method)


def _should_skip_remote_templates_for_general_chat(
    state: ApprovalState, user: UserContext
) -> bool:
    """远程凭证下，明显普通聊天不预拉 ERP 模板，直接进入通用对话。"""
    return should_skip_remote_templates_for_general_chat(state, user)


def _looks_like_remote_template_search(message: str) -> bool:
    """避免把普通聊天问候误当作 ERP 模板关键词。"""
    return looks_like_remote_template_search(message)


def _looks_like_general_question(message: str) -> bool:
    """识别帮助类/问答类输入，避免误触发发起审批。"""
    return looks_like_general_question(message)


def _uses_default_search_method() -> bool:
    """测试中 monkeypatch 旧 list 方法时，保持旧路径兼容。"""
    return uses_default_search_method(crm_approval_service)


def _is_remote_keyword_search_result(state: ApprovalState) -> bool:
    """识别可直接采用 ERP keyword 查询结果的首轮远程模板列表。"""
    return is_remote_keyword_search_result(state)


def _select_template_candidate(
    text: str,
    candidates: list[ApprovalTemplate],
    answer: dict[str, object] | None = None,
) -> ApprovalTemplate | None:
    """根据用户回复的序号、ID 或名称选择远程审批模板。"""
    return select_template_candidate(text, candidates, answer)


def _select_template_candidate_by_text(
    text: str, candidates: list[ApprovalTemplate]
) -> ApprovalTemplate | None:
    """按序号、ID、内部类型或名称匹配候选模板。"""
    cleaned = text.strip()
    if cleaned.isdigit():
        number = int(cleaned)
        if 1 <= number <= len(candidates):
            return candidates[number - 1]
    for template in candidates:
        markers = [
            template.template_id or "",
            template.approval_type,
            template.title,
            *template.aliases,
        ]
        if any(marker and marker in cleaned for marker in markers):
            return template
    return None


def _user_from_state(state: ApprovalState) -> UserContext:
    """从图状态中反序列化或重建用户上下文。"""
    return user_from_state(state, crm_approval_service)


def _template_detail_for_state(
    state: ApprovalState,
    approval_type: str,
    user: UserContext,
) -> ApprovalTemplate:
    """返回当前模板详情，优先复用本轮或会话缓存，减少远程重复请求。"""
    return template_detail_for_state(state, approval_type, user, crm_approval_service)


def _first_missing_field(
    template: ApprovalTemplate, slots: dict[str, str]
) -> str | None:
    """返回第一个尚未收集的模板必填字段。"""
    for field in template.fields:
        if field.required and (not slots.get(field.name)):
            return field.name
    return None


def _slots_from_structured_answer(
    answer: dict[str, object] | None,
    awaiting_field: str | None,
    collected_slots: dict[str, str] | None = None,
) -> tuple[dict[str, str], dict[str, object]]:
    """将前端结构化控件答案转换为展示值和提交值。"""
    return slots_from_structured_answer(answer, awaiting_field, collected_slots)


def _clear_dependent_fields(
    slots: dict[str, str],
    collected_values: dict[str, object],
    changed_fields: object,
) -> None:
    """字段被修改后清掉依赖字段，避免预览/提交旧值。"""
    clear_dependent_fields(slots, collected_values, changed_fields, FIELD_DEPENDENCIES)


def _awaiting_input_for_state(state: ApprovalState) -> AwaitingInput | None:
    """构建前端可渲染的当前等待控件描述。"""
    return awaiting_input_for_state(state, crm_approval_service)


def _awaiting_input_type_for_field(field) -> str:
    """根据内部字段模型选择前端输入控件类型。"""
    return awaiting_input_type_for_field(field)


def _awaiting_input_min(field, state: ApprovalState):
    """为结束时间提供最小值约束。"""
    return awaiting_input_min(field, state)


def _awaiting_value_schema(input_type: str) -> dict[str, str] | None:
    """返回复杂控件 value 的结构说明。"""
    return awaiting_value_schema(input_type)


def _template_choice_input(templates: list[ApprovalTemplate]) -> AwaitingInput | None:
    """构建审批模板候选单选控件。"""
    return template_choice_input(templates)


def _form_value_from_slots(slots: dict[str, str]) -> list[dict[str, str]]:
    """将已收集字段转换为 getNodes 需要的 form_value。"""
    return form_value_from_slots(slots)


def _nodes_from_state(state: ApprovalState) -> list[ApprovalNode]:
    """从状态中反序列化审批节点。"""
    return nodes_from_state(state)


def _awaiting_assignee_node_id(awaiting_field: str | None) -> str | None:
    """从等待字段标记中解析审批节点 ID。"""
    return awaiting_assignee_node_id(awaiting_field)


def _select_assignees_from_answer(
    node: ApprovalNode,
    answer: dict[str, object] | None,
) -> list[ApprovalAssignee]:
    """根据前端结构化选择从候选审批人中取值。"""
    return select_assignees_from_answer(node, answer)


def _select_assignees_from_message(
    node: ApprovalNode,
    message: str,
) -> list[ApprovalAssignee]:
    """根据用户消息从候选审批人中选择匹配项。"""
    return select_assignees_from_message(node, message)


def _first_unselected_node(
    nodes: list[ApprovalNode],
    selected_assignees: dict[str, list[str]],
) -> ApprovalNode | None:
    """返回第一个需要用户选择且尚未选择审批人的节点。"""
    return first_unselected_node(nodes, selected_assignees)


def _assignee_selection_message(node: ApprovalNode) -> str:
    """构建审批人选择追问文案。"""
    return assignee_selection_message(node)


def _assignee_selection_input(node: ApprovalNode) -> AwaitingInput:
    """构建审批节点办理人选择控件。"""
    return assignee_selection_input(node)


def _assignee_preview_fields(
    nodes: list[ApprovalNode],
    selected_assignees: dict[str, list[str]],
) -> list[PreviewField]:
    """构建审批人预览字段。"""
    return assignee_preview_fields(nodes, selected_assignees)


def _build_preview(
    template: ApprovalTemplate,
    slots: dict[str, str],
    approval_node: str | None,
    warnings: list[str],
) -> ApprovalPreview:
    """构建结构化审批预览响应模型。"""
    return build_preview(template, slots, approval_node, warnings)


def _submission_slots(state: ApprovalState) -> dict[str, object]:
    """合并展示字段和结构化字段，供 ERP 提交使用。"""
    return submission_slots(state)


def _approval_type_clarification(templates: list[ApprovalTemplate]) -> str:
    """构建列出可用审批分类的澄清消息。"""
    return approval_type_clarification(templates)


def _template_choice_message(templates: list[ApprovalTemplate]) -> str:
    """构建多个远程审批模板的选择提示。"""
    return template_choice_message(templates)


def _crm_error_message(error: str) -> str:
    """将 CRM 接口错误转换为用户可理解的聊天提示。"""
    return crm_error_message(error)


def _to_response(state: ApprovalState) -> ChatResponse:
    """将图状态转换为对外聊天响应结构。"""
    return to_chat_response(state, crm_approval_service)


def _field_labels_for_state(
    state: ApprovalState, field_names: list[str]
) -> dict[str, str]:
    """根据当前模板把字段 key 转换为用户可读名称。"""
    return field_labels_for_state(state, field_names, crm_approval_service)


def _labels_from_template(template: ApprovalTemplate) -> dict[str, str]:
    """从模板字段中抽取字段 key 到展示名称的映射。"""
    return labels_from_template(template)


def _actions_for_status(status: str) -> list[str]:
    """根据当前审批状态返回 UI 动作提示。"""
    return actions_for_status(status)


def _build_idempotency_key(state: ApprovalState) -> str:
    """构建用于模拟提交去重的确定性键。"""
    return build_idempotency_key(state)

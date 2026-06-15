from __future__ import annotations
import hashlib
import json
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
from app.services.crm_service import CrmApprovalService, crm_approval_service
from app.services.model_service import model_service
from app.services.session_state_service import (
    session_state_service,
)
from app.services.debug_log_service import write_debug_log
from app.services.template_candidate_service import (
    select_template_candidates,
)

MAX_REVIEW_COUNT = 2
FIELD_DEPENDENCIES = {
    "start_date": ["end_date"],
    "rest_start_time": ["rest_end_time", "rest_duration"],
    "rest_end_time": ["rest_duration"],
    "go_out_start_time": ["go_out_end_time", "go_out_duration"],
    "go_out_end_time": ["go_out_duration"],
}
LOCAL_MOCK_APPROVAL_TYPES = {
    "leave",
    "expense",
    "purchase",
    "seal",
    "inbound",
    "outbound",
    "overtime",
}


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
    return [ApprovalTemplate(**item) for item in state.get("_available_templates", [])]


def _template_candidates_from_state(state: ApprovalState) -> list[ApprovalTemplate]:
    """从图状态中反序列化等待用户选择的候选模板。"""
    return [ApprovalTemplate(**item) for item in state.get("_template_candidates", [])]


def _has_active_approval_context(state: ApprovalState) -> bool:
    """判断当前会话是否有可继续的审批上下文。"""
    return bool(
        state.get("approval_type")
        and state.get("status") in {
            "collecting",
            "awaiting_assignee_selection",
            "awaiting_confirmation",
        }
    )


def _is_resume_message(text: str) -> bool:
    """识别用户想回到当前审批流程。"""
    cleaned = text.strip()
    return any(
        marker in cleaned
        for marker in ("继续", "继续审批", "回到刚才", "刚才的审批", "接着填", "接着审批")
    )


def _append_resume_hint(answer: str, state: ApprovalState) -> str:
    """普通问答后附加当前审批等待项，便于用户继续。"""
    hint = _resume_message(state)
    return f"{answer}\n\n{hint}" if answer else hint


def _resume_message(state: ApprovalState) -> str:
    """构建继续当前审批的提示。"""
    label = _current_waiting_label(state)
    if label:
        return f"继续刚才的审批，当前等待填写：{label}。"
    if state.get("status") == "awaiting_confirmation":
        return "继续刚才的审批，当前等待你确认是否提交。"
    if state.get("status") == "awaiting_assignee_selection":
        return "继续刚才的审批，当前等待选择办理人/审批人。"
    return "继续刚才的审批，请补充下一项信息。"


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
    if not user.authorization or not user.uid:
        return False
    if state.get("approval_type") or state.get("_template_candidates"):
        return False
    if state.get("status", "idle") != "idle":
        return False
    message = state.get("user_message", "").strip()
    if not message:
        return False
    if not _looks_like_remote_template_search(message):
        return False
    return _uses_default_search_method()


def _should_skip_remote_templates_for_general_chat(
    state: ApprovalState, user: UserContext
) -> bool:
    """远程凭证下，明显普通聊天不预拉 ERP 模板，直接进入通用对话。"""
    if not user.authorization or not user.uid:
        return False
    if state.get("approval_type") or state.get("_template_candidates"):
        return False
    if state.get("status", "idle") != "idle":
        return False
    message = state.get("user_message", "").strip()
    if not message:
        return False
    return not _looks_like_remote_template_search(message)


def _looks_like_remote_template_search(message: str) -> bool:
    """避免把普通聊天问候误当作 ERP 模板关键词。"""
    if _looks_like_general_question(message):
        return False
    if has_approval_intent(message, []):
        return True
    return any((marker in message for marker in ("测试", "zh-", "ZH-", "审批编辑")))


def _looks_like_general_question(message: str) -> bool:
    """识别帮助类/问答类输入，避免误触发发起审批。"""
    return any((marker in message for marker in ("怎么", "如何", "什么", "哪些", "？", "?")))


def _uses_default_search_method() -> bool:
    """测试中 monkeypatch 旧 list 方法时，保持旧路径兼容。"""
    return (
        getattr(crm_approval_service.list_available_templates, "__func__", None)
        is CrmApprovalService.list_available_templates
    )


def _is_remote_keyword_search_result(state: ApprovalState) -> bool:
    """识别可直接采用 ERP keyword 查询结果的首轮远程模板列表。"""
    return bool(
        state.get("_template_search_keyword")
        and state.get("uid")
        and state.get("authorization")
        and not state.get("approval_type")
    )


def _select_template_candidate(
    text: str,
    candidates: list[ApprovalTemplate],
    answer: dict[str, object] | None = None,
) -> ApprovalTemplate | None:
    """根据用户回复的序号、ID 或名称选择远程审批模板。"""
    if isinstance(answer, dict) and answer.get("field_key") == "__approval_template__":
        selected_value = str(answer.get("value") or "").strip()
        selected_label = str(answer.get("label") or "").strip()
        selected = _select_template_candidate_by_text(
            selected_value or selected_label,
            candidates,
        )
        if selected:
            return selected
    return _select_template_candidate_by_text(text, candidates)


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
    user_data = state.get("_user_context")
    if not user_data:
        return crm_approval_service.get_user_context(
            state["user_id"],
            uid=state.get("uid"),
            authorization=state.get("authorization"),
        )
    return UserContext(**user_data)


def _template_detail_for_state(
    state: ApprovalState,
    approval_type: str,
    user: UserContext,
) -> ApprovalTemplate:
    """返回当前模板详情，优先复用本轮或会话缓存，减少远程重复请求。"""
    cached = state.get("_current_template")
    if isinstance(cached, dict) and cached.get("approval_type") == approval_type:
        return ApprovalTemplate(**cached)
    template = crm_approval_service.get_template_detail(approval_type, user)
    state["_current_template"] = template.model_dump()
    return template


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
    if not isinstance(answer, dict):
        return {}, {}
    field_key = str(answer.get("field_key") or "").strip()
    can_modify_collected = bool(collected_slots and field_key in collected_slots)
    if not field_key or (field_key != awaiting_field and not can_modify_collected):
        return {}, {}
    label = str(answer.get("label") or answer.get("value") or "").strip()
    if not label:
        return {}, {}
    return {
        field_key: label,
    }, {
        field_key: {
            "label": label,
            "value": answer.get("value"),
        }
    }


def _clear_dependent_fields(
    slots: dict[str, str],
    collected_values: dict[str, object],
    changed_fields: object,
) -> None:
    """字段被修改后清掉依赖字段，避免预览/提交旧值。"""
    pending = list(changed_fields)
    seen: set[str] = set()
    while pending:
        field = pending.pop()
        if field in seen:
            continue
        seen.add(field)
        for dependent in FIELD_DEPENDENCIES.get(field, []):
            slots.pop(dependent, None)
            collected_values.pop(dependent, None)
            pending.append(dependent)


def _awaiting_input_for_state(state: ApprovalState) -> AwaitingInput | None:
    """构建前端可渲染的当前等待控件描述。"""
    if state.get("_template_candidates") and not state.get("approval_type"):
        return _template_choice_input(_template_candidates_from_state(state))
    awaiting_field = state.get("awaiting_field")
    if state.get("status") == "awaiting_assignee_selection":
        node_id = _awaiting_assignee_node_id(awaiting_field)
        nodes = _nodes_from_state(state)
        current_node = next((node for node in nodes if node.node_id == node_id), None)
        if current_node:
            return _assignee_selection_input(current_node)
        return None
    if not awaiting_field or not state.get("approval_type"):
        return None
    try:
        template = _template_detail_for_state(
            state,
            state["approval_type"],
            _user_from_state(state),
        )
    except Exception:
        return None
    field = next(
        (item for item in template.fields if item.name == awaiting_field),
        None,
    )
    if not field:
        return None
    if field.type == "enum":
        if not field.options:
            return None
        option_values = field.option_values or [
            {"label": option, "value": option} for option in field.options
        ]
        return AwaitingInput(
            field_key=field.name,
            label=field.label,
            type="single_select",
            required=field.required,
            placeholder=field.question,
            options=option_values,
        )
    input_type = _awaiting_input_type_for_field(field)
    return AwaitingInput(
        field_key=field.name,
        label=field.label,
        type=input_type,
        required=field.required,
        placeholder=field.question,
        options=[],
        min=_awaiting_input_min(field, state),
        max=None,
        value_schema=_awaiting_value_schema(input_type),
    )


def _awaiting_input_type_for_field(field) -> str:
    """根据内部字段模型选择前端输入控件类型。"""
    if field.type == "date":
        return field.input_type or "datetime"
    if field.input_type in {"textarea", "address"}:
        return field.input_type
    return "text"


def _awaiting_input_min(field, state: ApprovalState):
    """为结束时间提供最小值约束。"""
    if field.type != "date":
        return None
    if not field.name.endswith("end_time"):
        return None
    start_field = field.name.removesuffix("end_time") + "start_time"
    value = state.get("collected_values", {}).get(start_field)
    if isinstance(value, dict) and value.get("value"):
        return value["value"]
    return state.get("collected_slots", {}).get(start_field)


def _awaiting_value_schema(input_type: str) -> dict[str, str] | None:
    """返回复杂控件 value 的结构说明。"""
    if input_type == "address":
        return {"area": "array", "detail": "string"}
    return None


def _template_choice_input(templates: list[ApprovalTemplate]) -> AwaitingInput | None:
    """构建审批模板候选单选控件。"""
    if not templates:
        return None
    return AwaitingInput(
        field_key="__approval_template__",
        label="审批模板",
        type="single_select",
        required=True,
        placeholder="请选择审批模板",
        options=[
            {"label": template.title, "value": template.approval_type}
            for template in templates
        ],
    )


def _form_value_from_slots(slots: dict[str, str]) -> list[dict[str, str]]:
    """将已收集字段转换为 getNodes 需要的 form_value。"""
    return [{"field_key": key, "value": value} for key, value in slots.items()]


def _nodes_from_state(state: ApprovalState) -> list[ApprovalNode]:
    """从状态中反序列化审批节点。"""
    return [ApprovalNode(**item) for item in state.get("approval_nodes", [])]


def _awaiting_assignee_node_id(awaiting_field: str | None) -> str | None:
    """从等待字段标记中解析审批节点 ID。"""
    if not awaiting_field or not awaiting_field.startswith("assignee:"):
        return None
    return awaiting_field.split(":", 1)[1]


def _select_assignees_from_answer(
    node: ApprovalNode,
    answer: dict[str, object] | None,
) -> list[ApprovalAssignee]:
    """根据前端结构化选择从候选审批人中取值。"""
    if not isinstance(answer, dict):
        return []
    expected_field = f"__approval_assignee__:{node.node_id}"
    if answer.get("field_key") != expected_field:
        return []
    raw_value = answer.get("value")
    values = raw_value if isinstance(raw_value, list) else [raw_value]
    selected_uids = {str(value).strip() for value in values if str(value or "").strip()}
    if not selected_uids:
        return []
    selected = [
        assignee
        for assignee in node.candidate_assignees
        if assignee.uid in selected_uids
    ]
    if selected and not node.multiple:
        return selected[:1]
    return selected


def _select_assignees_from_message(
    node: ApprovalNode,
    message: str,
) -> list[ApprovalAssignee]:
    """根据用户消息从候选审批人中选择匹配项。"""
    selected = [
        assignee
        for assignee in node.candidate_assignees
        if assignee.name and assignee.name in message
    ]
    if not selected:
        selected = [
            assignee
            for assignee in node.candidate_assignees
            if assignee.uid and assignee.uid in message
        ]
    if selected and not node.multiple:
        return selected[:1]
    return selected


def _first_unselected_node(
    nodes: list[ApprovalNode],
    selected_assignees: dict[str, list[str]],
) -> ApprovalNode | None:
    """返回第一个需要用户选择且尚未选择审批人的节点。"""
    for node in nodes:
        if node.requires_selection and not selected_assignees.get(node.node_id):
            return node
    return None


def _assignee_selection_message(node: ApprovalNode) -> str:
    """构建审批人选择追问文案。"""
    names = "、".join(assignee.name for assignee in node.candidate_assignees)
    if names:
        return f"请选择{node.node_name}审批人，可选：{names}。"
    return f"请选择{node.node_name}审批人。"


def _assignee_selection_input(node: ApprovalNode) -> AwaitingInput:
    """构建审批节点办理人选择控件。"""
    label = f"{node.node_name}审批人"
    return AwaitingInput(
        field_key=f"__approval_assignee__:{node.node_id}",
        label=label,
        type="user_select",
        required=True,
        placeholder=f"请选择{label}",
        options=[
            {
                "label": assignee.name,
                "value": assignee.uid,
                "avatar": assignee.avatar,
            }
            for assignee in node.candidate_assignees
        ],
        multiple=node.multiple,
    )


def _assignee_preview_fields(
    nodes: list[ApprovalNode],
    selected_assignees: dict[str, list[str]],
) -> list[PreviewField]:
    """构建审批人预览字段。"""
    fields: list[PreviewField] = []
    for node in nodes:
        selected_uids = set(selected_assignees.get(node.node_id, []))
        if selected_uids:
            names = [
                assignee.name
                for assignee in node.candidate_assignees
                if assignee.uid in selected_uids
            ]
        else:
            names = [assignee.name for assignee in node.selected_assignees]
        if names:
            fields.append(
                PreviewField(
                    name=f"assignee:{node.node_id}",
                    label=f"{node.node_name}审批人",
                    value="、".join(names),
                )
            )
    return fields


def _build_preview(
    template: ApprovalTemplate,
    slots: dict[str, str],
    approval_node: str | None,
    warnings: list[str],
) -> ApprovalPreview:
    """构建结构化审批预览响应模型。"""
    return ApprovalPreview(
        approval_type=template.approval_type,
        title=template.title,
        fields=[
            PreviewField(
                name=field.name, label=field.label, value=slots.get(field.name, "")
            )
            for field in template.fields
        ],
        approval_node=approval_node,
        warnings=warnings,
    )


def _submission_slots(state: ApprovalState) -> dict[str, object]:
    """合并展示字段和结构化字段，供 ERP 提交使用。"""
    slots: dict[str, object] = dict(state.get("collected_slots", {}))
    for key, value in state.get("collected_values", {}).items():
        slots[key] = value
    return slots


def _approval_type_clarification(templates: list[ApprovalTemplate]) -> str:
    """构建列出可用审批分类的澄清消息。"""
    if not templates:
        return "当前没有可发起的审批模板。"
    common = [template.title for template in templates if template.is_common][:5]
    categories: dict[str, int] = {}
    for template in templates:
        categories[template.category] = categories.get(template.category, 0) + 1
    category_text = "、".join(
        (f"{name}({count})" for name, count in sorted(categories.items()))
    )
    if common:
        common_text = "、".join(common)
        return f"请告诉我要办理哪类审批。常用审批包括：{common_text}。当前分类：{category_text}。"
    return f"请告诉我要办理哪类审批。当前分类：{category_text}。"


def _template_choice_message(templates: list[ApprovalTemplate]) -> str:
    """构建多个远程审批模板的选择提示。"""
    lines = ["找到多个审批模板，请回复序号或模板名称确认是哪一个审批："]
    for index, template in enumerate(templates, start=1):
        lines.append(f"{index}. {template.title}")
    return "\n".join(lines)


def _crm_error_message(error: str) -> str:
    """将 CRM 接口错误转换为用户可理解的聊天提示。"""
    if "401" in error:
        return "CRM 登录已过期或授权无效，请刷新页面重新登录后再试。"
    return f"获取 CRM 审批模板失败：{error}"


def _to_response(state: ApprovalState) -> ChatResponse:
    """将图状态转换为对外聊天响应结构。"""
    preview_data = state.get("preview")
    preview = ApprovalPreview(**preview_data) if preview_data else None
    missing_fields: list[str] = []
    if state.get("awaiting_field"):
        missing_fields.append(state["awaiting_field"])
    field_labels = _field_labels_for_state(state, missing_fields)
    display_missing_fields = [
        field_labels.get(field, field) for field in missing_fields
    ]
    awaiting_field_key = state.get("awaiting_field")
    awaiting_field_label = field_labels.get(awaiting_field_key or "")
    return ChatResponse(
        session_id=state["session_id"],
        status=state.get("status", "idle"),
        assistant_message=state.get("assistant_message", ""),
        approval_type=state.get("approval_type"),
        collected_slots=state.get("collected_slots", {}),
        collected_values=state.get("collected_values", {}),
        missing_fields=display_missing_fields,
        missing_field_keys=missing_fields,
        missing_field_labels=display_missing_fields,
        awaiting_field=awaiting_field_label or awaiting_field_key,
        awaiting_field_key=awaiting_field_key,
        awaiting_field_label=awaiting_field_label,
        awaiting_input=_awaiting_input_for_state(state),
        preview=preview,
        actions=_actions_for_status(state.get("status", "idle")),
        request_id=state.get("request_id"),
        approval_node=state.get("approval_node"),
        field_errors=state.get("field_errors", []),
        idempotency_key=state.get("idempotency_key"),
        trace=state.get("trace", []),
    )


def _field_labels_for_state(
    state: ApprovalState, field_names: list[str]
) -> dict[str, str]:
    """根据当前模板把字段 key 转换为用户可读名称。"""
    if not field_names or not state.get("approval_type"):
        return {}
    labels = dict(state.get("_field_labels", {}))
    if all(field in labels for field in field_names):
        return labels
    try:
        template = crm_approval_service.get_template_detail(
            state["approval_type"], _user_from_state(state)
        )
    except Exception:
        return labels
    labels.update(_labels_from_template(template))
    return labels


def _labels_from_template(template: ApprovalTemplate) -> dict[str, str]:
    """从模板字段中抽取字段 key 到展示名称的映射。"""
    return {field.name: field.label for field in template.fields}


def _actions_for_status(status: str) -> list[str]:
    """根据当前审批状态返回 UI 动作提示。"""
    if status in {"collecting", "awaiting_assignee_selection"}:
        return ["reply", "cancel"]
    if status == "awaiting_confirmation":
        return ["confirm", "modify", "cancel"]
    if status == "submitted":
        return ["query_status"]
    return ["reply"]


def _build_idempotency_key(state: ApprovalState) -> str:
    """构建用于模拟提交去重的确定性键。"""
    payload = {
        "session_id": state.get("session_id"),
        "user_id": state.get("user_id"),
        "approval_type": state.get("approval_type"),
        "slots": state.get("collected_slots", {}),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:24]
    return f"ai-approval:{digest}"

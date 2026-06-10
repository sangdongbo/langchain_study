from __future__ import annotations
import hashlib
import json
from langgraph.graph import END, START, StateGraph
from ai_approval_assistant.app.graph.extractors import (
    classify_approval_type,
    extract_slots,
    has_approval_intent,
    is_cancel_message,
    is_confirm_message,
    is_switch_message,
)
from ai_approval_assistant.app.graph.state import ApprovalState, initial_state
from ai_approval_assistant.app.schemas.approval import (
    ApprovalAssignee,
    ApprovalNode,
    ApprovalTemplate,
    UserContext,
)
from ai_approval_assistant.app.schemas.chat import (
    ApprovalPreview,
    ChatRequest,
    ChatResponse,
    PreviewField,
)
from ai_approval_assistant.app.services.crm_service import crm_approval_service
from ai_approval_assistant.app.services.model_service import model_service
from ai_approval_assistant.app.services.session_state_service import (
    session_state_service,
)
from ai_approval_assistant.app.services.template_candidate_service import (
    select_template_candidates,
)

MAX_REVIEW_COUNT = 2


def run_chat_turn(request: ChatRequest) -> ChatResponse:
    """将单轮聊天请求放入审批工作流图执行。"""
    state = session_state_service.load(request.session_id, request.user_id)
    state["session_id"] = request.session_id
    state["user_id"] = request.user_id
    state["uid"] = request.uid
    state["authorization"] = request.authorization
    state["user_message"] = request.message.strip()
    state["trace"] = []
    graph = create_workflow()
    result = graph.invoke(state)
    session_state_service.save(result)
    return _to_response(result)


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
    """识别用户消息并选择下一步工作流路由。"""
    trace = [*state.get("trace", []), "classify"]
    text = state["user_message"]
    status = state.get("status", "idle")
    if status == "submitted":
        return {**state, "trace": trace, "_route": "already_submitted"}
    if status in {
        "collecting",
        "awaiting_confirmation",
        "awaiting_assignee_selection",
    } and is_cancel_message(text):
        return {**state, "trace": trace, "_route": "cancel"}
    if status == "awaiting_assignee_selection":
        return {**state, "trace": trace, "_route": "assignee"}
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
    template = crm_approval_service.get_template_detail(approval_type, user)
    slots = dict(state.get("collected_slots", {}))
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
    template = crm_approval_service.get_template_detail(approval_type, user)
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
            selected = _select_assignees_from_message(current_node, state.get("user_message", ""))
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
    template = crm_approval_service.get_template_detail(state["approval_type"], user)
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
    template = crm_approval_service.get_template_detail(state["approval_type"], user)
    idempotency_key = state.get("idempotency_key") or _build_idempotency_key(state)
    result = crm_approval_service.submit_approval(
        state["approval_type"],
        state.get("collected_slots", {}),
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
    return {
        **state,
        "status": "idle",
        "approval_type": None,
        "collected_slots": {},
        "awaiting_field": None,
        "preview": None,
        "assistant_message": model_service.chat(state.get("user_message", "")),
        "trace": trace,
        "_route": "end",
    }


def _route(state: ApprovalState) -> str:
    """从状态中读取下一步图路由。"""
    return state.get("_route", "end")


def _templates_from_state(state: ApprovalState) -> list[ApprovalTemplate]:
    """从图状态中反序列化可用模板。"""
    return [ApprovalTemplate(**item) for item in state.get("_available_templates", [])]


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


def _first_missing_field(
    template: ApprovalTemplate, slots: dict[str, str]
) -> str | None:
    """返回第一个尚未收集的模板必填字段。"""
    for field in template.fields:
        if field.required and (not slots.get(field.name)):
            return field.name
    return None


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


def _to_response(state: ApprovalState) -> ChatResponse:
    """将图状态转换为对外聊天响应结构。"""
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

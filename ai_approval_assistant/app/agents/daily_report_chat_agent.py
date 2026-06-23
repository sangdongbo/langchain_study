from __future__ import annotations

from copy import deepcopy

from langgraph.types import interrupt

from app.agents.daily_report_common import (
    preview_message,
    report_date_from_state,
    user_from_daily_report_state,
)
from app.agents.daily_report.action_agent import daily_report_action_agent
from app.graph.extractors import is_confirm_message
from app.graph.state import ApprovalState
from app.services.daily_report_service import DailyReportSubmitError
from app.tools import daily_report_tools

daily_report_service = daily_report_tools.daily_report_service


def daily_report_chat_agent_node(state: ApprovalState) -> ApprovalState:
    """兼容旧调用路径：执行日报子图。"""
    from app.graph.daily_report_workflow import create_daily_report_workflow

    # 测试会 monkeypatch 旧模块里的 daily_report_service，这里同步给 tools，
    # 让旧入口和新子图共用同一套服务实例。
    daily_report_tools.daily_report_service = daily_report_service
    result = create_daily_report_workflow().invoke(state)
    # 直接调用旧入口时没有 ChatApplicationService 帮忙拆 interrupt，
    # 所以这里把 LangGraph 的中断结果还原成旧测试期望的普通 state。
    if "__interrupt__" in result:
        return _state_from_daily_report_interrupt(result)
    return result


def daily_report_entry_node(state: ApprovalState) -> ApprovalState:
    """日报子图入口：标记进入日报流程。"""
    trace = [*state.get("trace", []), "daily_report_chat_agent"]
    return {
        **state,
        "intent": "daily_report",
        "trace": [*trace, "daily_report_entry"],
    }


def daily_report_action_node(state: ApprovalState) -> ApprovalState:
    """判断本轮日报流程应该进入哪个业务阶段。"""
    trace = [*state.get("trace", []), "daily_report_action"]
    current_state = {**state, "trace": trace}
    action = daily_report_action_agent.classify(current_state)
    return {
        **current_state,
        "daily_report_action": action.action,
        "daily_report_action_source": action.source,
        "_route": action.route,
    }


def load_daily_report_context_node(state: ApprovalState) -> ApprovalState:
    """加载日报字段、配置、草稿和同步数据。"""
    trace = [*state.get("trace", []), "load_daily_report_context"]
    user = user_from_daily_report_state(state)
    report_type = int(state.get("daily_report_type") or 1)
    report_date = report_date_from_state(state)
    context = daily_report_tools.load_daily_report_context.invoke(
        {
            "user_id": user.user_id,
            "uid": user.uid,
            "authorization": user.authorization,
            "report_type": report_type,
            "report_date": report_date,
        }
    )
    payload = deepcopy(context.get("default_payload") or {})
    # 以后端请求入参为准，避免 ERP 草稿回包里残留旧日期时覆盖用户选择。
    payload["type"] = report_type
    payload["date"] = report_date
    explicit_content = _explicit_daily_report_content(state.get("user_message", ""))
    if explicit_content:
        payload["content"] = explicit_content
    if not str(payload.get("content") or "").strip():
        return _ask_for_daily_report_content({**state, "trace": trace}, payload)
    return {
        **state,
        "trace": trace,
        "awaiting_field": None,
        "daily_report_date": payload.get("date") or report_date,
        "daily_report_payload": payload,
        "_route": "save",
    }


def collect_daily_report_content_node(state: ApprovalState) -> ApprovalState:
    """收集或修改日报工作内容。"""
    trace = [*state.get("trace", []), "collect_daily_report_content"]
    current_state = {**state, "trace": trace}
    if (
        current_state.get("status") == "awaiting_daily_report_confirmation"
        and _is_modify_action(current_state)
    ):
        prompted = _ask_for_daily_report_content(
            current_state,
            deepcopy(current_state.get("daily_report_payload") or {}),
            message="请修改日志的工作内容，提交后我会重新给你确认。",
        )
        resumed = _maybe_interrupt(prompted)
        if resumed is None:
            return prompted
        payload = deepcopy(prompted.get("daily_report_payload") or {})
        payload["content"] = str(resumed or "").strip()
        return {
            **prompted,
            "awaiting_field": None,
            "daily_report_payload": payload,
            "ui_action": None,
            "_route": "save",
        }
    if current_state.get("awaiting_field") == "daily_report_content":
        return _preview_with_followup_content(current_state)
    if current_state.get("status") == "awaiting_daily_report_confirmation":
        return _modify_confirmation_content(current_state)
    payload = deepcopy(current_state.get("daily_report_payload") or {})
    if not str(payload.get("content") or "").strip():
        return _ask_for_daily_report_content(current_state, payload)
    return {**current_state, "_route": "save"}


def collect_daily_report_date_node(state: ApprovalState) -> ApprovalState:
    """收集或修改日报日期，日期变化后重新加载当天上下文。"""
    trace = [*state.get("trace", []), "collect_daily_report_date"]
    current_state = {**state, "trace": trace}
    if current_state.get("awaiting_field") == "daily_report_date":
        return _reload_with_followup_date(current_state)
    prompted = _ask_for_daily_report_date(current_state)
    resumed = _maybe_interrupt(prompted)
    if resumed is None:
        return prompted
    return {
        **prompted,
        "daily_report_date": str(resumed or "").strip(),
        "awaiting_field": None,
        "ui_action": None,
        "_route": "load",
    }


def save_daily_report_draft_node(state: ApprovalState) -> ApprovalState:
    """把当前日报 payload 保存为 ERP 草稿。"""
    trace = [*state.get("trace", []), "save_daily_report_draft"]
    payload = deepcopy(state.get("daily_report_payload") or {})
    user = user_from_daily_report_state(state)
    daily_report_tools.save_daily_report_draft.invoke(
        {
            "user_id": user.user_id,
            "uid": user.uid,
            "authorization": user.authorization,
            "payload": payload,
        }
    )
    return {
        **state,
        "daily_report_payload": payload,
        "trace": trace,
        "_route": "preview",
    }


def preview_daily_report_node(state: ApprovalState) -> ApprovalState:
    """生成日报确认预览。"""
    trace = [*state.get("trace", []), "preview_daily_report"]
    payload = deepcopy(state.get("daily_report_payload") or {})
    user = user_from_daily_report_state(state)
    preview = daily_report_tools.preview_daily_report_payload.invoke(
        {
            "user_id": user.user_id,
            "uid": user.uid,
            "authorization": user.authorization,
            "payload": payload,
        }
    )
    message = preview_message(payload, preview)
    ui_action = {
        **_interrupt_ui_action(
            field_key="daily_report_confirmation",
            label="确认提交",
            input_type="action",
            value=None,
            message=message,
        ),
        "actions": ["confirm", "modify", "modify_date", "cancel"],
    }
    return {
        **state,
        "status": "awaiting_daily_report_confirmation",
        "awaiting_field": None,
        "daily_report_date": payload.get("date") or state.get("daily_report_date"),
        "daily_report_payload": payload,
        "daily_report_preview": preview,
        "assistant_message": message,
        "ui_action": ui_action,
        "trace": trace,
        "_route": "end",
    }


def submit_daily_report_node(state: ApprovalState) -> ApprovalState:
    """提交已确认的日报。"""
    trace = [*state.get("trace", []), "submit_daily_report"]
    if is_confirm_message(state.get("user_message", "")):
        user = user_from_daily_report_state(state)
        try:
            result = daily_report_tools.submit_daily_report_payload.invoke(
                {
                    "user_id": user.user_id,
                    "uid": user.uid,
                    "authorization": user.authorization,
                    "payload": state.get("daily_report_payload") or {},
                }
            )
        except DailyReportSubmitError as exc:
            message = str(exc)
            return {
                **state,
                "status": "error",
                "assistant_message": f"日报提交失败：{message}",
                "field_errors": [{"field": "daily_report", "message": message}],
                "trace": trace,
                "_route": "end",
            }
        return {
            **state,
            "status": "daily_report_submitted",
            "daily_report_request_id": result.get("report_id"),
            "assistant_message": f"已提交日报。\n\n- 日报编号：{result.get('report_id') or '无'}\n- 当前状态：{result.get('status')}",
            "trace": trace,
            "_route": "end",
        }
    return {
        **state,
        "assistant_message": "提交前需要你明确回复“确认提交”。",
        "trace": trace,
        "_route": "end",
    }


def cancel_daily_report_node(state: ApprovalState) -> ApprovalState:
    """取消本轮日报提交。"""
    trace = [*state.get("trace", []), "cancel_daily_report"]
    return {
        **state,
        "status": "cancelled",
        "awaiting_field": None,
        "assistant_message": "已取消本次日报提交。",
        "ui_action": None,
        "trace": trace,
        "_route": "end",
    }


def _preview_with_followup_content(state: ApprovalState) -> ApprovalState:
    payload = deepcopy(state.get("daily_report_payload") or {})
    payload["content"] = _content_from_answer(state.get("_answer")) or state.get(
        "user_message", ""
    ).strip()
    if not str(payload.get("content") or "").strip():
        return _ask_for_daily_report_content(state, payload)
    return {
        **state,
        "awaiting_field": None,
        "daily_report_payload": payload,
        "_route": "save",
    }


def _reload_with_followup_date(state: ApprovalState) -> ApprovalState:
    report_date = _date_from_answer(state.get("_answer")) or state.get(
        "user_message", ""
    ).strip()
    if not report_date:
        return _ask_for_daily_report_date(state)
    return {
        **state,
        "daily_report_date": report_date,
        "awaiting_field": None,
        "_route": "load",
    }


def _modify_confirmation_content(state: ApprovalState) -> ApprovalState:
    payload = deepcopy(state.get("daily_report_payload") or {})
    content = _content_from_answer(state.get("_answer")) or _modify_content_from_message(
        state.get("user_message", "")
    )
    if not content:
        return {
            **state,
            "assistant_message": "可以继续说明要修改的工作内容，或回复“确认提交”。",
            "_route": "end",
        }
    payload["content"] = content
    if not str(payload.get("content") or "").strip():
        return _ask_for_daily_report_content(state, payload)
    return {
        **state,
        "awaiting_field": None,
        "daily_report_payload": payload,
        "_route": "save",
    }


def _ask_for_daily_report_content(
    state: ApprovalState,
    payload: dict,
    message: str = "今天还没有可提交的工作内容，请补充日志的工作内容。",
) -> ApprovalState:
    value = payload.get("content", "")
    ui_action = _interrupt_ui_action(
        field_key="daily_report_content",
        label="工作内容",
        input_type="textarea",
        value=value,
        message=message,
    )
    return {
        **state,
        "status": "collecting",
        "awaiting_field": "daily_report_content",
        "daily_report_payload": payload,
        "assistant_message": message,
        "ui_action": ui_action,
        "_route": "interrupt",
    }


def _ask_for_daily_report_date(
    state: ApprovalState,
    message: str = "请选择要填写日报的日期，我会重新获取当天草稿。",
) -> ApprovalState:
    payload = deepcopy(state.get("daily_report_payload") or {})
    value = payload.get("date") or state.get("daily_report_date")
    ui_action = _interrupt_ui_action(
        field_key="daily_report_date",
        label="日志时间",
        input_type="date",
        value=value,
        message=message,
    )
    return {
        **state,
        "status": "collecting",
        "awaiting_field": "daily_report_date",
        "daily_report_date": value,
        "daily_report_payload": payload,
        "assistant_message": message,
        "ui_action": ui_action,
        "_route": "interrupt",
    }


def _interrupt_ui_action(
    *,
    field_key: str,
    label: str,
    input_type: str,
    value,
    message: str,
) -> dict:
    return {
        "type": "interrupt",
        "field_key": field_key,
        "label": label,
        "input_type": input_type,
        "required": True,
        "value": value,
        "message": message,
    }


def _maybe_interrupt(state: ApprovalState):
    payload = state.get("ui_action")
    if not isinstance(payload, dict):
        return None
    # interrupt 只会把 payload 交给外层，嵌套子图的完整 state 不一定能直接
    # 出现在父图响应里；附带最小 state patch 供 API 层恢复成可保存的会话状态。
    interrupt_payload = {
        **payload,
        "_state_patch": _interrupt_state_patch(state),
    }
    try:
        return interrupt(interrupt_payload)
    except RuntimeError:
        return None


def interrupt_daily_report_node(state: ApprovalState) -> ApprovalState:
    """LangGraph 原生 interrupt 节点；resume 后保持当前 state 返回给外层。"""
    _maybe_interrupt(state)
    return {**state, "_route": "end"}


def _interrupt_state_patch(state: ApprovalState) -> dict:
    payload = state.get("daily_report_payload") or {}
    # 只携带前端恢复和会话持久化需要的日报字段，避免把整份 graph state 塞进
    # ui_action，同时保持返回给前端的 ui_action 仍然是干净的弹窗协议。
    return {
        "status": state.get("status"),
        "awaiting_field": state.get("awaiting_field"),
        "daily_report_date": state.get("daily_report_date") or payload.get("date"),
        "daily_report_payload": deepcopy(payload),
        "daily_report_preview": deepcopy(state.get("daily_report_preview") or {}),
        "assistant_message": state.get("assistant_message", ""),
    }


def _state_from_daily_report_interrupt(result: ApprovalState) -> ApprovalState:
    interrupts = result.get("__interrupt__") or []
    interrupt_value = getattr(interrupts[0], "value", {}) if interrupts else {}
    payload = interrupt_value if isinstance(interrupt_value, dict) else {}
    state_patch = (
        payload.get("_state_patch") if isinstance(payload.get("_state_patch"), dict) else {}
    )
    # _state_patch 是内部桥接字段，不能暴露给前端 ui_action。
    ui_action = {key: value for key, value in payload.items() if key != "_state_patch"}
    return {
        **{key: value for key, value in result.items() if key != "__interrupt__"},
        **state_patch,
        "ui_action": ui_action or result.get("ui_action"),
        "_route": "end",
    }


def _explicit_daily_report_content(message: str) -> str:
    text = message.strip()
    if is_confirm_message(text):
        return ""
    for separator in ("：", ":"):
        if separator in text:
            prefix, content = text.split(separator, 1)
            if _looks_like_daily_report_command(prefix):
                return content.strip()
    return ""


def _content_from_answer(answer) -> str:
    if not isinstance(answer, dict):
        return ""
    if answer.get("field_key") != "daily_report_content":
        return ""
    return str(answer.get("value") or answer.get("label") or "").strip()


def _date_from_answer(answer) -> str:
    if not isinstance(answer, dict):
        return ""
    if answer.get("field_key") != "daily_report_date":
        return ""
    return str(answer.get("value") or answer.get("label") or "").strip()


def _is_modify_date_action(state: ApprovalState) -> bool:
    answer = state.get("_answer")
    if isinstance(answer, dict) and answer.get("field_key") == "action":
        value = str(answer.get("value") or answer.get("label") or "").strip()
        if value in {"modify_date", "修改日期", "编辑日期", "edit_date"}:
            return True
    return state.get("user_message", "").strip() in {"修改日期", "编辑日期", "改日期"}


def _is_modify_action(state: ApprovalState) -> bool:
    answer = state.get("_answer")
    if isinstance(answer, dict) and answer.get("field_key") == "action":
        value = str(answer.get("value") or answer.get("label") or "").strip()
        if value in {"modify", "修改", "重新编辑", "edit"}:
            return True
    return state.get("user_message", "").strip() in {"修改", "重新编辑", "编辑内容"}


def _modify_content_from_message(message: str) -> str:
    text = message.strip()
    if is_confirm_message(text):
        return ""
    for marker in ("工作内容改成", "工作内容改为", "内容改成", "内容改为", "改成", "改为"):
        if marker in text:
            return text.split(marker, 1)[1].strip(" ：:")
    return ""


def _looks_like_daily_report_command(text: str) -> bool:
    return any(marker in text for marker in ("写日报", "写日志", "填日报", "填日志"))

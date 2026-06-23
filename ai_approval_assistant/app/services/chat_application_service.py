from __future__ import annotations

import traceback

from langgraph.types import Command

from app.agents.approval.constants import LOCAL_MOCK_APPROVAL_TYPES
from app.agents.approval.responses import to_chat_response
from app.graph.workflow import get_workflow
from app.graph.state import ApprovalState, initial_state
from app.schemas.chat import ChatRequest, ChatResponse
from app.services.crm_service import crm_approval_service
from app.services.debug_log_service import write_debug_log
from app.services.session_state_service import session_state_service
from app.services.short_term_memory_service import append_assistant_message
from app.services.time_travel_service import time_travel_service


class ChatApplicationService:
    """聊天应用服务：编排会话状态、工作流执行和响应持久化。"""

    def run_turn(self, request: ChatRequest) -> ChatResponse:
        """处理一轮聊天请求。"""
        # 记录原始入参，方便按 session_id 排查线上问题。
        write_debug_log("chat.request", request.model_dump())

        state = initial_state(request.session_id, request.user_id)
        try:
            # 先恢复会话状态；没有历史状态时由 session_state_service 创建初始状态。
            state = session_state_service.load(request.session_id, request.user_id)

            # 本地 mock 审批流切换到真实 ERP 凭证时，清理旧的本地审批上下文。
            if self._should_reset_local_state_for_remote_credentials(state, request):
                state = initial_state(request.session_id, request.user_id)

            # 把本轮 HTTP 请求转换成 graph 可消费的 AgentState 字段。
            state["session_id"] = request.session_id
            state["user_id"] = request.user_id
            state["uid"] = request.uid
            state["authorization"] = request.authorization
            state["user_message"] = request.message.strip()
            state["_answer"] = request.answer
            state["trace"] = []

            # 执行正式生产 graph，内部会根据 intent_router 进入对应业务 agent。
            graph = get_workflow()
            config = self._graph_config(request.session_id)
            # 前端回传 interrupt 弹窗答案时，用 Command(resume=...) 回到暂停节点，
            # 而不是重新从 START 跑一遍流程。
            graph_input = (
                Command(resume=self._resume_value(request.answer))
                if self._should_resume_interrupt(state, request)
                else state
            )
            result = graph.invoke(graph_input, config=config)
            if "__interrupt__" in result:
                # 嵌套子图 interrupt 时，返回体里只有中断对象；需要从 checkpoint
                # 和中断 payload 中合并出 API 可返回、可保存的完整状态。
                result = self._state_from_interrupt(
                    state,
                    request,
                    result,
                    graph.get_state(config).values,
                )

            # 将内部 AgentState 转换成接口响应模型，避免 API 直接暴露状态细节。
            response = to_chat_response(result, crm_approval_service)

            # 保存助手回复到短期记忆，再持久化完整会话状态。
            append_assistant_message(result, response.assistant_message)
            session_state_service.save(result)
            self._record_time_travel_checkpoint(result, request.message.strip())

            # 记录最终响应，和 chat.request 配对用于排查。
            write_debug_log("chat.response", response.model_dump())
            return response
        except Exception as exc:
            response = self._error_response(request, state, exc)
            write_debug_log(
                "chat.error",
                {
                    "session_id": request.session_id,
                    "user_id": request.user_id,
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "trace": state.get("trace", []),
                    "traceback": traceback.format_exc(),
                },
            )
            write_debug_log("chat.response", response.model_dump())
            return response

    def _error_response(
        self, request: ChatRequest, state: ApprovalState, exc: Exception
    ) -> ChatResponse:
        """把未捕获的业务异常转成稳定响应，避免前端只看到 HTTP 500。"""
        message = str(exc) or type(exc).__name__
        trace = [*state.get("trace", []), "chat_error"]
        return ChatResponse(
            session_id=request.session_id,
            status="error",
            assistant_message=f"智能助手处理失败：{message}",
            field_errors=[{"field": "chat", "message": message}],
            trace=trace,
        )

    def _record_time_travel_checkpoint(
        self, state: ApprovalState, user_message: str
    ) -> None:
        """记录学习版时光回溯 checkpoint；失败不影响主聊天流程。"""
        try:
            time_travel_service.record(state, user_message=user_message)
        except Exception as exc:
            write_debug_log(
                "time_travel.record.error",
                {
                    "session_id": state.get("session_id"),
                    "user_id": state.get("user_id"),
                    "error": str(exc),
                },
            )

    def _graph_config(self, session_id: str) -> dict:
        # thread_id 是 LangGraph checkpointer 区分会话线程的核心标识。
        return {"configurable": {"thread_id": session_id}}

    def _should_resume_interrupt(self, state: ApprovalState, request: ChatRequest) -> bool:
        ui_action = state.get("ui_action")
        return bool(
            request.answer
            and isinstance(ui_action, dict)
            and ui_action.get("type") == "interrupt"
        )

    def _resume_value(self, answer: dict | None):
        if not isinstance(answer, dict):
            return answer
        return answer.get("value", answer)

    def _state_from_interrupt(
        self,
        previous_state: ApprovalState,
        request: ChatRequest,
        result: dict,
        snapshot_values: dict,
    ) -> ApprovalState:
        interrupts = result.get("__interrupt__") or []
        interrupt = interrupts[0] if interrupts else None
        payload = getattr(interrupt, "value", None)
        if not isinstance(payload, dict):
            payload = {"message": "请补充信息。"}
        # _state_patch 是日报子图传给后端的内部状态补丁，前端 ui_action 不展示它。
        state_patch = payload.get("_state_patch") if isinstance(payload.get("_state_patch"), dict) else {}
        ui_action = {key: value for key, value in payload.items() if key != "_state_patch"}
        field_key = str(payload.get("field_key") or "")
        message = str(payload.get("message") or previous_state.get("assistant_message") or "")
        interrupted_state = {
            key: value for key, value in result.items() if key != "__interrupt__"
        }
        if snapshot_values:
            # checkpoint 里保存的是 interrupt 发生前的父图快照，先用它补齐基础状态。
            interrupted_state = {
                **interrupted_state,
                **snapshot_values,
            }
        if state_patch:
            # 子图内部最新的日报 payload/preview 要覆盖父图快照里的旧值。
            interrupted_state = {
                **interrupted_state,
                **state_patch,
            }
        status = (
            "awaiting_daily_report_confirmation"
            if field_key == "daily_report_confirmation"
            else "collecting"
        )
        awaiting_field = None if field_key == "daily_report_confirmation" else field_key
        return {
            **previous_state,
            **interrupted_state,
            "session_id": request.session_id,
            "user_id": request.user_id,
            "uid": request.uid,
            "authorization": request.authorization,
            "user_message": request.message.strip(),
            "_answer": request.answer,
            "status": status,
            "awaiting_field": awaiting_field,
            "assistant_message": message,
            "ui_action": ui_action,
            "trace": [
                *interrupted_state.get("trace", previous_state.get("trace", [])),
                "langgraph_interrupt",
            ],
        }

    def _should_reset_local_state_for_remote_credentials(
        self, state: ApprovalState, request: ChatRequest
    ) -> bool:
        """真实 ERP 凭证进入后，丢弃旧的本地模拟审批会话。"""
        if not request.authorization or not request.uid:
            return False
        approval_type = state.get("approval_type")
        return bool(approval_type and approval_type in LOCAL_MOCK_APPROVAL_TYPES)


chat_application_service = ChatApplicationService()

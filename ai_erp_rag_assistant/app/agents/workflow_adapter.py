"""把 DeepAgent Harness 适配为聊天路由使用的 LangGraph 风格接口。"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
import json
from typing import Any, Literal, cast

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.runnables import RunnableConfig
from langgraph.checkpoint.memory import MemorySaver

from ai_erp_rag_assistant.app.agents.harness import create_erp_agent_harness
from ai_erp_rag_assistant.app.graph.state import ErpRagState
from ai_erp_rag_assistant.app.services.model_service import model_service


_ERP_STATE_KEYS = frozenset(ErpRagState.__annotations__)
_HISTORY_MAX_MESSAGES = 16
_HISTORY_MAX_CHARS = 12_000

# DeepAgents 的 task 工具会把子代理的结构化结果放在
# ``structured_response`` 中；这里只允许业务状态白名单字段回写根图，避免
# 将 task 的内部字段、认证信息或文件系统结果带回聊天状态。
_STRUCTURED_STATE_KEYS = {
    "evidence",
    "citations",
    "assistant_message",
    "workflow_status",
    "pending_question",
    "preview",
    "form_schema",
    "template_candidates",
    "template_selection_required",
    "erp_data",
    "errors",
}


def _message_text(message: AIMessage) -> str:
    """兼容纯文本和内容块格式，只提取最终用户可见文本。"""
    if isinstance(message.content, str):
        return message.content.strip()
    if not isinstance(message.content, list):
        return ""
    return "".join(
        str(item.get("text") or item.get("content") or "")
        if isinstance(item, dict)
        else str(item)
        for item in message.content
    ).strip()


def _stream_text(message: Any) -> str:
    """提取流式消息正文并保留空白，供前端按原 Token 顺序拼接。"""
    content = getattr(message, "content", "")
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    return "".join(
        str(item.get("text") or item.get("content") or "")
        if isinstance(item, dict)
        else str(item)
        for item in content
    )


def _last_answer(messages: list[Any]) -> str:
    """跳过带工具调用的中间消息，避免把父 Agent 的内部计划暴露给前端。"""
    for message in reversed(messages):
        if isinstance(message, AIMessage) and not message.tool_calls:
            text = _message_text(message)
            if text:
                return text
    return ""


def _structured_mapping(value: Any) -> Mapping[str, Any]:
    """将 dict 或 Pydantic 结构化输出统一成只读映射。"""
    if isinstance(value, Mapping):
        return value
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        dumped = model_dump()
        return dumped if isinstance(dumped, Mapping) else {}
    return {}


def _structured_response(result: Mapping[str, Any]) -> Mapping[str, Any]:
    """读取顶层或 task 工具消息中的领域结构化结果。"""
    direct = _structured_mapping(result.get("structured_response"))
    if direct:
        return direct
    for message in reversed(list(result.get("messages", []))):
        if not isinstance(message, ToolMessage) or message.name != "task":
            continue
        content = message.content
        if not isinstance(content, str):
            continue
        try:
            payload = json.loads(content)
        except (TypeError, json.JSONDecodeError):
            continue
        if isinstance(payload, Mapping):
            return payload
    return {}


def _structured_state_updates(
    result: Mapping[str, Any],
    current_route: str,
) -> dict[str, Any]:
    """把领域子代理的结构化协议映射到现有 ErpRagState。"""
    payload = _structured_response(result)
    updates = {
        key: payload[key]
        for key in _STRUCTURED_STATE_KEYS
        if key in payload and key in _ERP_STATE_KEYS
    }
    status = payload.get("status")
    # RAG 使用 retrieval_status，审批/ERP 状态使用 workflow_status；不把
    # 通用 status 字段直接写入状态，避免破坏原有字段语义。
    if isinstance(status, str) and status:
        if current_route == "knowledge" and "retrieval_status" in _ERP_STATE_KEYS:
            updates["retrieval_status"] = status
        elif current_route in {"approval_workflow", "erp_status"}:
            updates["workflow_status"] = status
    if "message" in payload and "assistant_message" not in updates:
        updates["assistant_message"] = str(payload["message"] or "")
    return updates


def _history_messages(state: ErpRagState) -> list[Any]:
    """把持久化的脱敏对话恢复为有界的 user/assistant 消息。"""
    conversation = [
        item
        for item in state.get("conversation", [])
        if isinstance(item, Mapping)
        and item.get("role") in {"user", "assistant"}
        and str(item.get("content") or "")
    ]
    current = str(state.get("user_message") or "")
    if not conversation or not (
        conversation[-1].get("role") == "user"
        and str(conversation[-1].get("content") or "") == current
    ):
        conversation.append({"role": "user", "content": current})

    # 从最近消息向前分配字符预算，防止长期会话无限扩大模型上下文。
    bounded: list[tuple[str, str]] = []
    remaining = _HISTORY_MAX_CHARS
    for item in reversed(conversation[-_HISTORY_MAX_MESSAGES:]):
        if remaining <= 0:
            break
        content = str(item.get("content") or "")[:remaining]
        if content:
            bounded.append((str(item["role"]), content))
            remaining -= len(content)
    return [
        AIMessage(content=content) if role == "assistant" else HumanMessage(content=content)
        for role, content in reversed(bounded)
    ]


def _append_assistant_turn(state: ErpRagState) -> None:
    """把最终回答写入可持久化会话，并避免审批提示重复追加。"""
    message = str(state.get("assistant_message") or "")
    if not message:
        return
    conversation = list(state.get("conversation", []))
    if not (
        conversation
        and conversation[-1].get("role") == "assistant"
        and str(conversation[-1].get("content") or "") == message
    ):
        conversation.append({"role": "assistant", "content": message})
    state["conversation"] = conversation[-_HISTORY_MAX_MESSAGES:]


class DeepAgentWorkflowAdapter:
    """维持现有 ``invoke/stream/get_state`` 契约的轻量适配器。"""

    def __init__(self, agent: Any, *, restore_history: bool = False) -> None:
        self._agent = agent
        self._restore_history = restore_history

    def _input(self, state: ErpRagState) -> dict[str, Any]:
        # 内存会话由 Checkpointer 恢复消息；MySQL 长期会话使用脱敏 conversation，
        # 两种来源不能同时注入，否则同一轮历史会被重复发送给模型。
        messages = (
            _history_messages(state)
            if self._restore_history
            else [HumanMessage(content=state["user_message"])]
        )
        return {**state, "messages": messages}

    @staticmethod
    def _result(state: ErpRagState, result: Mapping[str, Any]) -> ErpRagState:
        merged = {
            **state,
            **{key: value for key, value in result.items() if key in _ERP_STATE_KEYS},
        }
        route = str(merged.get("route") or "unknown")
        # 子代理结果通常通过 task 工具返回，不能只依赖顶层字段；结构化结果
        # 只补充根状态白名单字段，顶层确定性字段仍保留更高优先级。
        structured_updates = _structured_state_updates(result, route)
        for key, value in structured_updates.items():
            if key not in result:
                # ``state`` 可能携带上一轮草稿；当前子代理的结构化结果才是
                # 本轮事实，因此允许它替换旧的临时字段。顶层确定性结果仍优先。
                merged[key] = value
        deterministic_message = str(merged.get("assistant_message") or "")
        generated_message = _last_answer(list(result.get("messages", [])))
        # 无证据拒答必须由代码保证，不能只依赖父 Agent 遵守 Prompt。
        if route == "knowledge" and not merged.get("evidence"):
            merged["assistant_message"] = model_service.answer(
                state.get("user_message", ""),
                route="knowledge",
                evidence=[],
            )
        # 审批提示来自确定性子图，不能被父 Agent 改写确认语义或提交结果。
        elif route != "approval_workflow" or not deterministic_message:
            merged["assistant_message"] = generated_message or deterministic_message
        if route == "unknown":
            merged["route"] = "general_chat"
        _append_assistant_turn(cast(ErpRagState, merged))
        return cast(ErpRagState, merged)

    def invoke(self, state: ErpRagState, *, config: RunnableConfig) -> ErpRagState:
        result = self._agent.invoke(self._input(state), config=config)
        return self._result(state, result)

    def stream(
        self,
        state: ErpRagState,
        *,
        config: RunnableConfig,
        stream_mode: Any = None,
    ) -> Iterator[tuple[str, Any]]:
        """运行原生 DeepAgent 流，并只释放已确认的最终父 Agent 回答。"""
        requested = (
            set(stream_mode)
            if isinstance(stream_mode, (list, tuple, set))
            else {str(stream_mode or "values")}
        )
        raw_result: Mapping[str, Any] | None = None
        final_turn: list[tuple[Any, dict[str, Any]]] = []
        final_turn_id: tuple[Any, Any] | None = None

        # 必须消费 messages 才能保留供应商真实 Token 边界，同时消费 values
        # 才能判断最后一轮是回答还是仍包含工具调用。
        for mode, value in self._agent.stream(
            self._input(state),
            config=config,
            stream_mode=["messages", "values"],
        ):
            if mode == "values" and isinstance(value, Mapping):
                raw_result = value
                continue
            if mode != "messages":
                continue
            message, metadata = value
            if metadata.get("langgraph_node") != "model":
                continue
            turn_id = (
                metadata.get("langgraph_checkpoint_ns"),
                metadata.get("langgraph_step"),
            )
            if turn_id != final_turn_id:
                final_turn = []
                final_turn_id = turn_id
            final_turn.append((message, dict(metadata)))

        if raw_result is None:
            raise RuntimeError("DeepAgent 流结束时没有返回最终状态")
        result = self._result(state, raw_result)
        answer = str(result.get("assistant_message") or "")
        streamed_answer = "".join(_stream_text(message) for message, _ in final_turn)

        if "messages" in requested and answer:
            # RAG/普通问答可复用真实模型 Chunk；审批回答必须使用确定性子图文本。
            if (
                result.get("route") != "approval_workflow"
                and streamed_answer.strip() == answer.strip()
            ):
                for message, metadata in final_turn:
                    if _stream_text(message):
                        yield "messages", (
                            message,
                            {
                                **metadata,
                                "langgraph_node": "answer_with_llm",
                                "deepagent_final": True,
                            },
                        )
            else:
                yield "messages", (
                    AIMessage(content=answer),
                    {
                        "langgraph_node": "answer_with_llm",
                        "deepagent_final": True,
                    },
                )
        if "values" in requested:
            yield "values", result

    def get_state(self, config: RunnableConfig) -> Any:
        return self._agent.get_state(config)


def create_deepagent_workflow(
    assistant_type: Literal["rag", "approval"],
    *,
    model_overrides: dict[str, Any] | None = None,
    system_context: str = "",
    with_checkpointer: bool = True,
) -> DeepAgentWorkflowAdapter:
    """创建聊天接口可直接使用的 DeepAgent 工作流。"""
    checkpointer = MemorySaver() if with_checkpointer else None
    return DeepAgentWorkflowAdapter(
        create_erp_agent_harness(
            assistant_type=assistant_type,
            model_overrides=model_overrides,
            system_context=system_context,
            checkpointer=checkpointer,
        ),
        restore_history=not with_checkpointer,
    )


def model_overrides_key(overrides: dict[str, Any] | None) -> str:
    """生成可用于路由缓存的稳定键，避免把可变字典直接作为 lru 参数。"""
    return json.dumps(overrides or {}, ensure_ascii=False, sort_keys=True, default=str)

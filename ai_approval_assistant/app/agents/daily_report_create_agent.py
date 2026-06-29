from __future__ import annotations

from datetime import date
from typing import Any, Callable

from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langchain_core.tools import tool
from langchain_deepseek import ChatDeepSeek
from pydantic import BaseModel, Field

from app.schemas.approval import UserContext
from app.graph.state import ApprovalState
from app.services.env_config_service import load_ai_approval_env
from app.tools import daily_report_tools
from app.tools.daily_report_tools import DAILY_REPORT_TOOLS


DAILY_REPORT_CREATE_AGENT_PROMPT = """你是 ERP 日报 create_agent 自主版本。

你的目标是帮助用户完成写日志/写日报，但必须遵守 ERP 写入边界：
1. 必须先确认日志日期；如果用户说“今天/今日”或没有指定明确日期，必须先调用 get_current_daily_report_date 获取后端权威当天日期，不要自己推断或编造日期。
2. 日期确认后，才能调用日报字段、配置、草稿和同步数据相关工具；调用 load_daily_report_context 时，report_date 必须使用已确认日期或 get_current_daily_report_date 返回的 date。
3. 生成或修改 content 后，应调用保存草稿工具，把当前日报 payload 写入 /oa/dailyReport/config/draft/set。
4. 提交 /oa/dailyReport/add 前，必须先给用户展示预览，并且用户明确确认提交后才允许提交。
5. 自定义字段必须保留在 extends 和 extend_fields 中，不要丢弃 extends、recipients、cc_recipients、files、at_uids。
6. 如果外部接口失败，直接说明失败接口和原因，不要假装已经保存或提交。

你可以自主选择工具，但不要绕过用户确认，也不要重复提交。"""


AgentBackend = Callable[..., Any]


def create_daily_report_create_agent(model: Any) -> Any:
    """创建 ERP 日报自主 Agent。

    这是独立实验版入口，不挂载到现有 create_daily_report_workflow。
    本地依赖没有 langchain.create_agent 时，会回退到 langgraph.prebuilt.create_react_agent。
    """
    backend = _create_agent_backend()
    return backend(
        model=model,
        tools=DAILY_REPORT_CREATE_AGENT_TOOLS,
        prompt=DAILY_REPORT_CREATE_AGENT_PROMPT,
    )


def daily_report_create_agent_node(state: ApprovalState) -> ApprovalState:
    """自主日报 Agent 节点：在主图中适配 ApprovalState 和 create_agent 消息协议。"""
    trace = [*state.get("trace", []), "daily_report_create_agent"]
    try:
        agent = create_daily_report_create_agent(_build_daily_report_create_model())
        result = agent.invoke({"messages": _agent_messages(state)})
    except Exception as exc:
        message = str(exc) or type(exc).__name__
        return {
            **state,
            "intent": "daily_report",
            "daily_report_mode": "autonomous",
            "status": "error",
            "assistant_message": f"自主日报 Agent 处理失败：{message}",
            "field_errors": [{"field": "daily_report", "message": message}],
            "trace": trace,
            "_route": "end",
        }
    assistant_message = _last_message_content(result) or "自主日报 Agent 已完成本轮处理。"
    return {
        **state,
        "intent": "daily_report",
        "daily_report_mode": "autonomous",
        "daily_report_agent_messages": _serializable_messages(_result_messages(result))
        or _serializable_messages(state.get("daily_report_agent_messages", [])),
        "status": _status_from_agent_message(assistant_message),
        "assistant_message": assistant_message,
        "trace": trace,
        "_route": "end",
    }


def _build_daily_report_create_model() -> ChatDeepSeek:
    """创建自主日报 Agent 使用的模型实例。"""
    import os

    load_ai_approval_env()
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("DEEPSEEK_API_KEY is not configured")
    return ChatDeepSeek(
        model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
        api_key=api_key,
        temperature=float(os.getenv("DEEPSEEK_TEMPERATURE", "0")),
        timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "30")),
        max_retries=1,
    )


def _agent_messages(state: ApprovalState) -> list[Any]:
    """把主图状态压成自主 Agent 的消息历史。"""
    return [
        *[_message_for_agent(message) for message in state.get("daily_report_agent_messages", [])],
        _agent_user_message(state),
    ]


def _agent_user_message(state: ApprovalState) -> dict[str, str]:
    """把本轮用户请求补充 ERP 上下文后传给自主 Agent。"""
    lines = [
        f"用户ID：{state.get('user_id', '')}",
        f"ERP UID：{state.get('uid') or ''}",
        f"ERP Authorization：{state.get('authorization') or ''}",
        "",
        state.get("user_message", ""),
    ]
    return {"role": "user", "content": "\n".join(lines)}


def _result_messages(result: Any) -> list[Any]:
    messages = result.get("messages", []) if isinstance(result, dict) else []
    return messages if isinstance(messages, list) else []


def _serializable_messages(messages: list[Any]) -> list[dict[str, Any]]:
    serializable = []
    for message in messages:
        serializable.append(_serializable_message(message))
    return serializable


def _serializable_message(message: Any) -> dict[str, Any]:
    if isinstance(message, dict):
        role = str(message.get("role") or message.get("type") or "user")
        content = _message_content_to_text(message.get("content"))
        item: dict[str, Any] = {"role": role, "content": content}
        if message.get("tool_call_id"):
            item["tool_call_id"] = str(message["tool_call_id"])
        if message.get("tool_calls"):
            item["tool_calls"] = message["tool_calls"]
        return item
    role = "assistant" if isinstance(message, AIMessage) else "tool" if isinstance(message, ToolMessage) else "user"
    item = {"role": role, "content": _message_content_to_text(getattr(message, "content", ""))}
    tool_call_id = getattr(message, "tool_call_id", None)
    if tool_call_id:
        item["tool_call_id"] = str(tool_call_id)
    tool_calls = getattr(message, "tool_calls", None)
    if tool_calls:
        item["tool_calls"] = tool_calls
    return item


def _message_for_agent(message: Any) -> Any:
    if not isinstance(message, dict):
        return message
    role = message.get("role")
    content = message.get("content", "")
    if role == "assistant":
        return AIMessage(content=content, tool_calls=message.get("tool_calls") or [])
    if role == "tool":
        return ToolMessage(content=content, tool_call_id=message.get("tool_call_id", "tool"))
    return HumanMessage(content=content)


def _last_message_content(result: Any) -> str:
    """从 create_agent / react_agent 返回值中取最后一条 AI 消息文本。"""
    messages = _result_messages(result)
    for message in reversed(messages):
        if not isinstance(message, AIMessage):
            continue
        content = _message_content_to_text(getattr(message, "content", None))
        if content.strip():
            return content.strip()
    for message in reversed(messages):
        if isinstance(message, dict) and message.get("role") not in {"assistant", "ai"}:
            continue
        content = _message_content_to_text(message.get("content") if isinstance(message, dict) else None)
        if content.strip():
            return content.strip()
    return ""


def _message_content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(item) for item in content)
    if content is None:
        return ""
    return str(content)


def _status_from_agent_message(message: str) -> str:
    if "已提交" in message:
        return "daily_report_submitted"
    if "确认" in message or "预览" in message:
        return "awaiting_daily_report_confirmation"
    return "idle"


def _create_agent_backend() -> AgentBackend:
    """优先使用 LangChain create_agent；不可用时使用 LangGraph prebuilt agent。"""
    try:
        from langchain.agents import create_agent

        return create_agent
    except ImportError:
        from langgraph.prebuilt import create_react_agent

        return create_react_agent


class GuardedSubmitDailyReportInput(BaseModel):
    user_id: str = Field(description="业务用户 ID。")
    payload: dict[str, Any] = Field(description="日报提交 payload。")
    confirmed: bool = Field(description="用户是否已明确确认提交。")
    uid: str | None = Field(default=None, description="ERP UID。")
    authorization: str | None = Field(default=None, description="ERP Authorization。")


@tool
def get_current_daily_report_date() -> dict[str, str]:
    """获取后端计算出的当前日报日期，格式为 YYYY-MM-DD。"""
    return {"date": date.today().isoformat()}


@tool(args_schema=GuardedSubmitDailyReportInput)
def guarded_submit_daily_report(
    user_id: str,
    payload: dict[str, Any],
    confirmed: bool,
    uid: str | None = None,
    authorization: str | None = None,
) -> dict[str, Any]:
    """仅在用户明确确认后提交日报，防止自主 agent 误触发 ERP 写入。"""
    if not confirmed:
        return {
            "code": 400,
            "message": "提交日报前必须先展示预览，并由用户明确确认提交。",
        }
    result = daily_report_tools.daily_report_service.submit_payload(
        _tool_user(user_id, uid, authorization),
        payload,
    )
    return result.model_dump()


def _tool_user(
    user_id: str,
    uid: str | None = None,
    authorization: str | None = None,
) -> UserContext:
    """构造日报工具所需的最小用户上下文。"""
    return UserContext(
        user_id=user_id,
        name=f"User {user_id}",
        company_id="",
        dept_id="",
        role="",
        manager_id="",
        uid=uid,
        authorization=authorization,
    )


DAILY_REPORT_CREATE_AGENT_TOOLS = [
    get_current_daily_report_date,
    *[tool for tool in DAILY_REPORT_TOOLS if tool.name != "submit_daily_report_payload"],
    guarded_submit_daily_report,
]

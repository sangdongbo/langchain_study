from __future__ import annotations

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from ai_deep_agents_assistant.app.services.model_service import build_chat_model
from ai_deep_agents_assistant.app.tools.approval_tools import APPROVAL_TOOLS


APPROVAL_AGENT_PROMPT = """
你是 AI 审批助手，负责帮助用户发起审批。

必须遵守：
1. 先调用 get_current_user_context 获取用户上下文。
2. 需要了解可用模板时，调用 list_approval_templates。
3. 收集审批字段时，调用 collect_approval_draft；不要自己猜字段是否完整。
4. draft 缺字段时，只追问第一个缺失字段。
5. draft 已生成 preview 后，必须让用户明确回复“确认提交”。
6. 只有用户明确确认后，才允许调用 submit_approval_request。
7. submit_approval_request 是危险工具，会被 human-in-the-loop 中断；不要绕过。
8. 输出中文，尽量给出结构化信息。
"""


checkpointer = MemorySaver()
_approval_deep_agent = None


def create_approval_deep_agent():
    """Create the Deep Agents approval assistant graph."""
    return create_deep_agent(
        model=build_chat_model(),
        tools=APPROVAL_TOOLS,
        system_prompt=APPROVAL_AGENT_PROMPT,
        checkpointer=checkpointer,
        interrupt_on={"submit_approval_request": True},
    )


def get_approval_deep_agent():
    """Return a lazily-created Deep Agents graph.

    Lazy creation keeps imports cheap for IDEs, tests and FastAPI startup checks.
    The real DeepSeek model is built only when the chat service actually runs.
    """
    global _approval_deep_agent
    if _approval_deep_agent is None:
        _approval_deep_agent = create_approval_deep_agent()
    return _approval_deep_agent

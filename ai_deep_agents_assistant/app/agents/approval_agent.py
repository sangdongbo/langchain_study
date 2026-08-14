from __future__ import annotations

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import MemorySaver

from ai_deep_agents_assistant.app.services.model_service import build_chat_model
from ai_deep_agents_assistant.app.tools.approval_tools import APPROVAL_TOOLS
from ai_deep_agents_assistant.app.tools.daily_report_tools import DAILY_REPORT_TOOLS


APPROVAL_AGENT_PROMPT = """
你是 AI Deep Agent 助手，负责帮助用户发起审批和填写日报。

必须遵守：
1. 先判断用户是在发起审批还是写日报，不要混用两类工具。
2. 处理审批时，先调用 get_current_user_context；需要模板时调用 list_approval_templates。
3. 收集审批字段时调用 collect_approval_draft，不要自己猜字段是否完整。
4. 处理“日报/日志”时，调用 collect_daily_report_draft 收集日期和工作内容。
5. 用户说“今天/今日”时，以 get_current_daily_report_date 返回的日期为准。
6. draft 缺字段时，只追问第一个缺失字段。
7. 日报草稿必须保留 ERP 返回的完整 payload，只能修改 date/content，不要丢失 extends、extend_fields、recipients、cc_recipients、files、at_uids。
8. draft 已生成 preview 后，应调用对应 submit 工具；提交工具会被 human-in-the-loop 中断并让用户确认。
9. submit_approval_request 和 submit_daily_report_request 都是危险工具，不要绕过中断。
10. 输出中文，尽量给出结构化信息，并明确当前处理的是审批还是日报。
"""


checkpointer = MemorySaver()
_approval_deep_agent = None


def create_approval_deep_agent():
    """创建 Deep Agents 审批助手图。"""
    return create_deep_agent(
        model=build_chat_model(),
        tools=[*APPROVAL_TOOLS, *DAILY_REPORT_TOOLS],
        system_prompt=APPROVAL_AGENT_PROMPT,
        checkpointer=checkpointer, # 状态检查
        interrupt_on={
            "submit_approval_request": True,
            "submit_daily_report_request": True,
        },
    )


def get_approval_deep_agent():
    """返回延迟创建的 Deep Agents 图。

    延迟创建可降低 IDE、测试和 FastAPI 启动检查时的导入开销。
    仅在聊天服务实际运行时创建真实的 DeepSeek 模型。
    """
    global _approval_deep_agent
    if _approval_deep_agent is None:
        _approval_deep_agent = create_approval_deep_agent()
    return _approval_deep_agent

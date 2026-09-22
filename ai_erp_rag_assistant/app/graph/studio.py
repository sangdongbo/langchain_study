"""为 LangGraph Studio 暴露根图和两个按能力隔离的 DeepAgent Harness。"""

from typing import Any

from ai_erp_rag_assistant.app.agents.harness import create_erp_agent_harness
from ai_erp_rag_assistant.app.graph.workflow import create_workflow


# LangGraph API 自己管理 Studio 线程持久化，因此这里不附加进程内 Checkpointer。
graph = create_workflow(with_checkpointer=False)


def create_rag_deepagent_graph() -> Any:
    """创建只允许知识检索子代理的 Studio Graph。"""
    return create_erp_agent_harness(assistant_type="rag")


def create_approval_deepagent_graph() -> Any:
    """创建只允许 ERP 状态和审批子代理的 Studio Graph。"""
    return create_erp_agent_harness(assistant_type="approval")

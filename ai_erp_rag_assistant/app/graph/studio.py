"""为 LangGraph Studio 暴露不带进程内 Checkpointer 的工作流实例。"""

from ai_erp_rag_assistant.app.graph.workflow import create_workflow


graph = create_workflow(with_checkpointer=False)

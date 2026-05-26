from __future__ import annotations

"""ERP Agent 的兼容导入文件。

早期代码可能写的是 `from streamlit_v2.erp_agent import ...`。
真正实现已经移动到 `streamlit_v2.agent.erp_agent`，这里保留转发，避免旧代码失效。
新代码请优先使用 `streamlit_v2.agent.erp_agent`。
"""

from erp_ask.agent.erp_agent import ERPAgentResponse, ERPFlowState, handle_erp_message


__all__ = ["ERPAgentResponse", "ERPFlowState", "handle_erp_message"]

from __future__ import annotations

"""ERP tools 的兼容导入文件。

工具注册表已经移动到 `streamlit_v2.tools.registry`。
这里保留旧路径转发，方便学习阶段逐步重构，不让旧 import 直接报错。
"""

from crm_ask_langsmith.tools.registry import get_tool, list_tools, run_tool


__all__ = ["get_tool", "list_tools", "run_tool"]

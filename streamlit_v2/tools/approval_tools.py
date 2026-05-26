from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.tools import tool


"""审批类 LangChain tool。

`@tool` 会把普通 Python 函数包装成 LangChain 可调用工具。
模型或规则 Agent 调用工具时，拿到的是结构化 dict，而不是页面文案。
"""


@tool("create_approval_request")
def create_approval_request(
    approval_type: str,
    title: str,
    reason: str,
    user_id: str = "U001",
) -> dict[str, Any]:
    """创建通用审批申请。

    Args:
        approval_type: 审批类型，例如采购、报销、用章、通用审批。
        title: 审批标题。
        reason: 审批原因或说明。
        user_id: 员工 ID。演示环境默认使用 U001。
    """

    # 演示环境没有真实审批系统，所以用时间戳生成一个看起来像业务编号的 ID。
    request_id = "AP-" + datetime.now().strftime("%Y%m%d%H%M%S")
    return {
        "source": "mock",
        "data": {
            "request_id": request_id,
            "user_id": user_id,
            "approval_type": approval_type,
            "title": title,
            "reason": reason,
            "status": "待审批",
            "approval_node": "直属主管审批",
        },
    }

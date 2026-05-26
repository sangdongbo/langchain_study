from __future__ import annotations

from datetime import datetime
from typing import Any

from langchain_core.tools import tool

from erp_ask.tools.mock_data import MOCK_USERS


"""请假相关 LangChain tools。

这里模拟 ERP 后端接口：查询假期余额、创建请假申请。
页面和 Agent 都不直接读 MOCK_USERS，而是通过工具函数访问数据。
"""


@tool("get_leave_balance")
def get_leave_balance(user_id: str = "U001") -> dict[str, Any]:
    """查询员工假期余额。

    Args:
        user_id: 员工 ID。演示环境默认使用 U001。
    """

    user = MOCK_USERS[user_id]
    # 统一返回 source/data 结构，方便测试和页面层处理。
    return {
        "source": "mock",
        "data": {
            "user_id": user_id,
            "user_name": user["name"],
            "balances": user["leave_balances"],
        },
    }


@tool("create_leave_request")
def create_leave_request(
    leave_type: str,
    start_date: str,
    end_date: str,
    reason: str,
    user_id: str = "U001",
) -> dict[str, Any]:
    """创建请假申请。

    Args:
        leave_type: 请假类型，例如年假、事假、病假、调休。
        start_date: 请假开始日期，格式 YYYY-MM-DD。
        end_date: 请假结束日期，格式 YYYY-MM-DD。
        reason: 请假原因。
        user_id: 员工 ID。演示环境默认使用 U001。
    """

    # 真实系统中 request_id 应该由后端数据库生成。
    request_id = "LR-" + datetime.now().strftime("%Y%m%d%H%M%S")
    return {
        "source": "mock",
        "data": {
            "request_id": request_id,
            "user_id": user_id,
            "leave_type": leave_type,
            "start_date": start_date,
            "end_date": end_date,
            "reason": reason,
            "status": "待审批",
            "approval_node": "直属主管审批",
        },
    }

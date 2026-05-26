from __future__ import annotations

from typing import Any


# 当前项目没有接真实 ERP，这里集中放本地演示数据。
# 真实接入时优先替换 tools/service 层，不要让 Agent 或页面读取这些 mock 数据。
MOCK_USERS: dict[str, dict[str, Any]] = {
    "U001": {
        "name": "测试员工",
        "leave_balances": {
            "年假": 12,
            "事假": 0,
            "病假": 5,
            "调休": 2,
        },
    }
}

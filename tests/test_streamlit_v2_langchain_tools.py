import unittest

from erp_ask.agent.erp_agent import ERPFlowState, handle_erp_message
from erp_ask.tools.registry import get_tool, list_tools, run_tool


"""streamlit_v2 的工具和规则 Agent 测试。

这些测试只走 mock 工具和本地规则，不调用真实模型，也不访问数据库。
"""


class StreamlitV2LangChainToolsTests(unittest.TestCase):
    def test_tools_are_registered_as_langchain_tools(self):
        """registry 应该暴露所有 ERP 演示工具。"""

        tools = list_tools()
        names = {tool.name for tool in tools}

        self.assertIn("get_leave_balance", names)
        self.assertIn("create_leave_request", names)
        self.assertIn("create_approval_request", names)
        self.assertTrue(callable(get_tool("get_leave_balance").invoke))

    def test_tool_registry_runs_leave_balance_tool(self):
        """run_tool 应该能执行假期余额工具并返回结构化结果。"""

        result = run_tool("get_leave_balance", {"user_id": "U001"})

        self.assertEqual("mock", result["source"])
        self.assertEqual(12, result["data"]["balances"]["年假"])

    def test_agent_uses_tool_registry_for_leave_balance(self):
        """询问假期余额时，规则 Agent 应直接返回业务话术。"""

        response, state = handle_erp_message("我还有几天年假", ERPFlowState())

        self.assertTrue(response.handled)
        self.assertIn("已为你查询到假期余额", response.message)
        self.assertNotIn("get_leave_balance", response.message)
        self.assertIsNone(state.intent)

    def test_sick_leave_request_asks_one_question_at_a_time(self):
        """请假申请缺字段时，应一次只追问一个字段。"""

        response, state = handle_erp_message("申请病假", ERPFlowState())

        self.assertTrue(response.handled)
        self.assertEqual("leave_request", state.intent)
        self.assertEqual("start_date", state.awaiting)
        self.assertEqual("病假", state.slots["leave_type"])
        self.assertIn("开始时间", response.message)
        self.assertNotIn("结束时间", response.message)
        self.assertNotIn("请假原因", response.message)

    def test_leave_request_collects_fields_before_submitting(self):
        """多轮请假流程应收齐开始时间、结束时间、原因后再提交。"""

        state = ERPFlowState(
            intent="leave_request",
            awaiting="start_date",
            slots={"leave_type": "病假"},
        )

        response, state = handle_erp_message("2026-06-01", state)
        self.assertTrue(response.handled)
        self.assertEqual("end_date", state.awaiting)
        self.assertIn("结束时间", response.message)
        self.assertNotIn("申请编号", response.message)

        response, state = handle_erp_message("2026-06-03", state)
        self.assertTrue(response.handled)
        self.assertEqual("reason", state.awaiting)
        self.assertEqual("2026-06-01", state.slots["start_date"])
        self.assertEqual("2026-06-03", state.slots["end_date"])
        self.assertIn("请假原因", response.message)
        self.assertNotIn("申请编号", response.message)

        response, state = handle_erp_message("发烧需要休息", state)
        self.assertTrue(response.handled)
        self.assertIn("已为你创建请假申请", response.message)
        self.assertIn("病假", response.message)
        self.assertIsNone(state.intent)


if __name__ == "__main__":
    unittest.main()

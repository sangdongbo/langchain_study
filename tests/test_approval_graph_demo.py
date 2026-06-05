import unittest

from approval_graph_demo.graph import create_approval_graph
from approval_graph_demo.state import ApprovalState


class ApprovalGraphDemoTests(unittest.TestCase):
    def test_leave_request_previews_before_submit_and_submits_after_confirmation(self):
        graph = create_approval_graph()
        state = ApprovalState()

        result = graph.invoke(
            {
                **state,
                "user_message": "我想申请病假，2026-06-01 到 2026-06-03，因为发烧需要休息",
            }
        )

        self.assertEqual("awaiting_confirmation", result["status"])
        self.assertIn("请确认是否提交请假申请", result["assistant_message"])
        self.assertIn("病假", result["assistant_message"])
        self.assertIsNone(result["request_id"])

        result = graph.invoke({**result, "user_message": "确认提交"})

        self.assertEqual("submitted", result["status"])
        self.assertIn("已提交请假申请", result["assistant_message"])
        self.assertTrue(result["request_id"].startswith("LR-"))

    def test_expense_request_can_modify_amount_before_confirmation(self):
        graph = create_approval_graph()
        state = ApprovalState()

        result = graph.invoke(
            {
                **state,
                "user_message": "我要报销差旅费，金额 3200，事由是客户拜访，发票已提供",
            }
        )

        self.assertEqual("awaiting_confirmation", result["status"])
        self.assertEqual("3200", result["slots"]["amount"])

        result = graph.invoke({**result, "user_message": "修改金额为 3000"})

        self.assertEqual("awaiting_confirmation", result["status"])
        self.assertEqual("3000", result["slots"]["amount"])
        self.assertIsNone(result["request_id"])
        self.assertIn("3000", result["assistant_message"])

        result = graph.invoke({**result, "user_message": "确认提交"})

        self.assertEqual("submitted", result["status"])
        self.assertTrue(result["request_id"].startswith("EX-"))

    def test_purchase_request_asks_missing_fields_one_at_a_time(self):
        graph = create_approval_graph()
        state = ApprovalState()

        result = graph.invoke({**state, "user_message": "我要申请采购笔记本电脑"})

        self.assertEqual("collecting", result["status"])
        self.assertEqual("quantity", result["awaiting"])
        self.assertIn("数量", result["assistant_message"])

        result = graph.invoke({**result, "user_message": "2 台"})

        self.assertEqual("collecting", result["status"])
        self.assertEqual("budget", result["awaiting"])
        self.assertIn("预算", result["assistant_message"])

    def test_leave_balance_query_does_not_start_purchase_or_approval(self):
        graph = create_approval_graph()
        state = ApprovalState()

        result = graph.invoke({**state, "user_message": "帮我查一下我的假期"})

        self.assertEqual("idle", result["status"])
        self.assertIsNone(result["approval_type"])
        self.assertIsNone(result["awaiting"])
        self.assertIn("假期余额", result["assistant_message"])
        self.assertNotIn("采购", result["assistant_message"])

    def test_collecting_flow_can_be_cancelled(self):
        graph = create_approval_graph()
        state = ApprovalState()

        result = graph.invoke({**state, "user_message": "我要申请采购笔记本电脑"})
        self.assertEqual("collecting", result["status"])
        self.assertEqual("quantity", result["awaiting"])

        result = graph.invoke({**result, "user_message": "我不想采购了"})

        self.assertEqual("cancelled", result["status"])
        self.assertIn("已取消", result["assistant_message"])
        self.assertIn("没有提交", result["assistant_message"])
        self.assertNotIn("采购数量", result["assistant_message"])

    def test_collecting_flow_can_switch_to_a_new_approval_type(self):
        graph = create_approval_graph()
        state = ApprovalState()

        result = graph.invoke({**state, "user_message": "我要申请采购笔记本电脑"})
        self.assertEqual("purchase", result["approval_type"])
        self.assertEqual("quantity", result["awaiting"])

        result = graph.invoke({**result, "user_message": "改成请年假，2026-06-10 到 2026-06-11，因为家里有事"})

        self.assertEqual("leave", result["approval_type"])
        self.assertEqual("awaiting_confirmation", result["status"])
        self.assertIn("请确认是否提交请假申请", result["assistant_message"])
        self.assertNotIn("采购数量", result["assistant_message"])

    def test_collecting_flow_does_not_switch_from_incidental_type_words(self):
        graph = create_approval_graph()
        state = ApprovalState()

        result = graph.invoke({**state, "user_message": "我要去报销"})
        self.assertEqual("expense", result["approval_type"])
        self.assertEqual("expense_type", result["awaiting"])

        result = graph.invoke({**result, "user_message": "我的采购数量是1个"})

        self.assertEqual("expense", result["approval_type"])
        self.assertEqual("expense_type", result["awaiting"])
        self.assertNotIn("amount", result["slots"])
        self.assertIn("报销类型", result["assistant_message"])
        self.assertNotIn("采购预算", result["assistant_message"])

        result = graph.invoke({**result, "user_message": "2000"})

        self.assertEqual("expense", result["approval_type"])
        self.assertEqual("expense_type", result["awaiting"])
        self.assertNotIn("amount", result["slots"])
        self.assertIn("报销类型", result["assistant_message"])

    def test_collecting_numeric_reply_does_not_reclassify_with_model(self):
        graph = create_approval_graph()
        state = ApprovalState()

        result = graph.invoke({**state, "user_message": "我要申请采购笔记本电脑"})
        result = graph.invoke({**result, "user_message": "1 个"})

        self.assertEqual("purchase", result["approval_type"])
        self.assertEqual("budget", result["awaiting"])

        result = graph.invoke({**result, "user_message": "2000"})

        self.assertEqual("purchase", result["approval_type"])
        self.assertEqual("purpose", result["awaiting"])
        self.assertIn("采购用途", result["assistant_message"])


if __name__ == "__main__":
    unittest.main()

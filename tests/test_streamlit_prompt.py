import unittest

from ai_companion.llm import build_prompt_messages
from ai_companion.chat_store import ChatMessage


class PromptTests(unittest.TestCase):
    def test_prompt_requires_assistant_to_accept_saved_nickname(self):
        messages = build_prompt_messages(
            "小黑",
            "回答直接、亲切。",
            [ChatMessage(role="user", content="你是不是叫小黑？")],
        )

        system_prompt = messages[0].content

        self.assertIn("你的昵称是：小黑", system_prompt)
        self.assertIn("用户询问你的名字时，必须承认这个昵称", system_prompt)
        self.assertIn("即使历史消息里出现过其他名字，也必须以当前昵称为准", system_prompt)
        self.assertIn("不要否认这个昵称", system_prompt)


if __name__ == "__main__":
    unittest.main()

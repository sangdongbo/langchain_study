import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from ai_companion.chat_store import ChatMessage, ConversationStore


class ConversationStoreTests(unittest.TestCase):
    def test_creates_and_persists_conversation_messages(self):
        with TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "conversations.json"
            store = ConversationStore(store_path)

            conversation = store.create_conversation("小黑", "性格火辣的四川姑娘")
            store.append_message(conversation.id, ChatMessage(role="user", content="你好"))
            store.append_message(conversation.id, ChatMessage(role="assistant", content="你好呀"))

            reloaded = ConversationStore(store_path)
            conversations = reloaded.list_conversations()

        self.assertEqual(len(conversations), 1)
        self.assertEqual(conversations[0].title, "小黑")
        self.assertEqual(conversations[0].persona, "性格火辣的四川姑娘")
        self.assertEqual([message.role for message in conversations[0].messages], ["user", "assistant"])
        self.assertEqual(conversations[0].messages[-1].content, "你好呀")

    def test_profile_update_is_used_by_later_messages(self):
        with TemporaryDirectory() as tmpdir:
            store_path = Path(tmpdir) / "conversations.json"
            store = ConversationStore(store_path)

            conversation = store.create_conversation("小黑", "旧性格")
            store.update_profile(conversation.id, "小白", "新性格")
            store.append_message(conversation.id, ChatMessage(role="user", content="你叫什么"))

            reloaded = ConversationStore(store_path)
            updated = reloaded.get_conversation(conversation.id)

        self.assertIsNotNone(updated)
        self.assertEqual(updated.title, "小白")
        self.assertEqual(updated.persona, "新性格")
        self.assertEqual(updated.messages[-1].content, "你叫什么")


if __name__ == "__main__":
    unittest.main()

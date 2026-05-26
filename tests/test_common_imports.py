from __future__ import annotations

from common.chat_store import ChatMessage, ConversationStore


def test_common_package_exports_shared_chat_helpers(tmp_path) -> None:
    store = ConversationStore(tmp_path / "conversations.json")
    conversation = store.create_conversation("测试助手", "认真回答问题")
    store.append_message(conversation.id, ChatMessage(role="user", content="你好"))

    messages = store.get_conversation(conversation.id).messages

    assert messages == [ChatMessage(role="user", content="你好")]

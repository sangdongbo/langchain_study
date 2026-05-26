from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


"""本地聊天记录存储。

Streamlit 页面每次交互都会重新执行脚本，所以聊天历史不能只放在普通变量里。
这个模块用 JSON 文件保存会话、助手设置和消息，页面刷新后也能恢复。
"""


@dataclass
class ChatMessage:
    """一条聊天消息。

    role 通常是 "user" 或 "assistant"；content 是实际文本。
    """

    role: str
    content: str


@dataclass
class Conversation:
    """一个完整会话，包括会话资料和消息列表。"""

    id: str
    title: str
    persona: str
    created_at: str
    messages: list[ChatMessage] = field(default_factory=list)


class ConversationStore:
    """负责把 Conversation 对象读写到 JSON 文件。"""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        # 第一次运行时缓存目录可能不存在，先创建父目录。
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_conversations(self) -> list[Conversation]:
        """读取所有会话，最新创建的会话排在列表前面。"""

        data = self._read_data()
        return [self._conversation_from_dict(item) for item in data.get("conversations", [])]

    def create_conversation(self, title: str, persona: str) -> Conversation:
        """创建新会话并写入缓存文件。"""

        conversation = Conversation(
            # 时间戳 + 随机片段，方便人读，也降低 ID 重复概率。
            id=datetime.now().strftime("%Y%m%d%H%M%S") + "-" + uuid.uuid4().hex[:6],
            title=title.strip() or "新的伙伴",
            persona=persona.strip() or "温柔、耐心、认真回答问题的 AI 伙伴",
            created_at=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            messages=[],
        )
        conversations = self.list_conversations()
        conversations.insert(0, conversation)
        self._write_conversations(conversations)
        return conversation

    def get_conversation(self, conversation_id: str) -> Conversation | None:
        """按 ID 查找一个会话，找不到时返回 None。"""

        for conversation in self.list_conversations():
            if conversation.id == conversation_id:
                return conversation
        return None

    def update_profile(self, conversation_id: str, title: str, persona: str) -> None:
        """更新会话的助手昵称和人设。"""

        conversations = self.list_conversations()
        for conversation in conversations:
            if conversation.id == conversation_id:
                conversation.title = title.strip() or conversation.title
                conversation.persona = persona.strip() or conversation.persona
                break
        self._write_conversations(conversations)

    def append_message(self, conversation_id: str, message: ChatMessage) -> None:
        """向指定会话追加一条消息。"""

        conversations = self.list_conversations()
        for conversation in conversations:
            if conversation.id == conversation_id:
                conversation.messages.append(message)
                break
        self._write_conversations(conversations)

    def delete_conversation(self, conversation_id: str) -> None:
        """删除指定会话。"""

        conversations = [
            conversation
            for conversation in self.list_conversations()
            if conversation.id != conversation_id
        ]
        self._write_conversations(conversations)

    def _read_data(self) -> dict:
        """读取 JSON 原始数据；文件不存在时返回空结构。"""

        if not self.path.exists():
            return {"conversations": []}
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write_conversations(self, conversations: list[Conversation]) -> None:
        """把 dataclass 对象转换为 JSON 可保存的 dict。"""

        payload = {
            "conversations": [
                {
                    **asdict(conversation),
                    "messages": [asdict(message) for message in conversation.messages],
                }
                for conversation in conversations
            ]
        }
        with self.path.open("w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2)

    @staticmethod
    def _conversation_from_dict(data: dict) -> Conversation:
        """把 JSON 里的 dict 还原成 Conversation 对象。"""

        return Conversation(
            id=data["id"],
            title=data["title"],
            persona=data["persona"],
            created_at=data["created_at"],
            messages=[ChatMessage(**message) for message in data.get("messages", [])],
        )

from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class Conversation:
    id: str
    title: str
    persona: str
    created_at: str
    messages: list[ChatMessage] = field(default_factory=list)


class ConversationStore:
    def __init__(self, path: Path | str) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def list_conversations(self) -> list[Conversation]:
        data = self._read_data()
        return [self._conversation_from_dict(item) for item in data.get("conversations", [])]

    def create_conversation(self, title: str, persona: str) -> Conversation:
        conversation = Conversation(
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
        for conversation in self.list_conversations():
            if conversation.id == conversation_id:
                return conversation
        return None

    def update_profile(self, conversation_id: str, title: str, persona: str) -> None:
        conversations = self.list_conversations()
        for conversation in conversations:
            if conversation.id == conversation_id:
                conversation.title = title.strip() or conversation.title
                conversation.persona = persona.strip() or conversation.persona
                break
        self._write_conversations(conversations)

    def append_message(self, conversation_id: str, message: ChatMessage) -> None:
        conversations = self.list_conversations()
        for conversation in conversations:
            if conversation.id == conversation_id:
                conversation.messages.append(message)
                break
        self._write_conversations(conversations)

    def delete_conversation(self, conversation_id: str) -> None:
        conversations = [
            conversation
            for conversation in self.list_conversations()
            if conversation.id != conversation_id
        ]
        self._write_conversations(conversations)

    def _read_data(self) -> dict:
        if not self.path.exists():
            return {"conversations": []}
        with self.path.open("r", encoding="utf-8") as file:
            return json.load(file)

    def _write_conversations(self, conversations: list[Conversation]) -> None:
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
        return Conversation(
            id=data["id"],
            title=data["title"],
            persona=data["persona"],
            created_at=data["created_at"],
            messages=[ChatMessage(**message) for message in data.get("messages", [])],
        )

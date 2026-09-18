"""Small tool-capable fake chat model shared by feature tests."""

from __future__ import annotations

import sys
from collections.abc import Sequence
from typing import Any

from langchain_core.language_models.fake_chat_models import FakeMessagesListChatModel
from langchain_core.tools import BaseTool
from pydantic import Field


def configure_utf8_output() -> None:
    """让 Windows IDE 和重定向终端正确显示中文测试结果。"""
    if reconfigure := getattr(sys.stdout, "reconfigure", None):
        reconfigure(encoding="utf-8")


class ToolCapableFakeModel(FakeMessagesListChatModel):
    """Let LangChain bind tools while preserving scripted responses and inputs."""

    seen_messages: list[list[Any]] = Field(default_factory=list)

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any] | type | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> ToolCapableFakeModel:
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        self.seen_messages.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)

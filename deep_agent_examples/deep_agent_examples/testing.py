"""供离线功能测试复用的、支持工具绑定的脚本化假模型。

测试可以预先写好模型响应，并检查每轮真正收到的消息；整个过程不调用真实
模型接口，也不会向 LangSmith 上传追踪数据。
"""

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
    """允许 LangChain 绑定工具，同时保留脚本化响应和每轮输入消息。"""

    # Pydantic 字段：按模型调用轮次保存消息快照，供测试断言中间件注入内容。
    seen_messages: list[list[Any]] = Field(default_factory=list)

    def bind_tools(
        self,
        tools: Sequence[BaseTool | dict[str, Any] | type | Any],
        *,
        tool_choice: str | None = None,
        **kwargs: Any,
    ) -> ToolCapableFakeModel:
        """接受框架的工具绑定请求，但继续返回当前假模型实例。"""
        return self

    def _generate(self, messages, stop=None, run_manager=None, **kwargs):
        """调用父类生成预设响应前，先记录本轮模型看到的完整消息。"""
        self.seen_messages.append(list(messages))
        return super()._generate(messages, stop, run_manager, **kwargs)

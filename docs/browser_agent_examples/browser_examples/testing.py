"""固定响应替身：检查真实 Agent/浏览器接口，不测试模型的规划能力。"""

from typing import Any

from browser_use import ChatOpenAI
from browser_use.llm.views import ChatInvokeCompletion


class ScriptedModel(ChatOpenAI):
    def __init__(self, actions: list[dict[str, Any]]) -> None:
        super().__init__(model="offline-scripted-model")
        self._verified_api_keys = True
        self.actions = iter(actions)
        self.calls = 0

    async def ainvoke(self, messages, output_format=None, **kwargs):
        if output_format is None:
            raise AssertionError("离线检查预期 Agent 请求结构化动作")
        self.calls += 1
        completion = output_format.model_validate({
            "evaluation_previous_goal": "执行固定测试动作",
            "memory": "离线集成检查",
            "next_goal": "验证本地浏览器接口",
            "action": [next(self.actions)],
        })
        return ChatInvokeCompletion(completion=completion, usage=None)

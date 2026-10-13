"""固定响应替身：检查真实 Agent/浏览器接口，不测试模型的规划能力。"""

from typing import Any

from browser_use import ChatOpenAI
from browser_use.llm.views import ChatInvokeCompletion


class ScriptedModel(ChatOpenAI):
    # 只替换“模型返回什么动作”；Agent 和 Chromium 仍执行真实浏览器操作。
    def __init__(self, actions: list[dict[str, Any]]) -> None:
        super().__init__(model="offline-scripted-model")
        # 测试替身不使用密钥，跳过模型适配器的密钥验证。
        self._verified_api_keys = True
        # 每次调用消费一个动作；动作耗尽会暴露意外的额外模型调用。
        self.actions = iter(actions)
        self.calls = 0

    async def ainvoke(self, messages, output_format=None, **kwargs):
        # 不调用父类 ainvoke，所以不会请求 API；也不依据 messages 做规划。
        if output_format is None:
            raise AssertionError("离线检查预期 Agent 请求结构化动作")
        self.calls += 1
        # 按 Agent 本次提供的动态 schema 校验动作，发现接口变化时直接失败。
        completion = output_format.model_validate({
            "evaluation_previous_goal": "执行固定测试动作",
            "memory": "离线集成检查",
            "next_goal": "验证本地浏览器接口",
            "action": [next(self.actions)],
        })
        # 没有真实模型请求，因此不提供 token 用量统计。
        return ChatInvokeCompletion(completion=completion, usage=None)

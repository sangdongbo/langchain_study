"""05：显式传递历史，在第二轮修改第一轮的采购数量。"""

from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from pydantic_examples.config import build_model

FIRST_PROMPT = "记住本次采购：4 台 AI 推理服务器，每台 68000 元。请确认数量和单价。"
SECOND_PROMPT = "数量改成 6 台，单价不变，现在总价是多少？"


def build_agent(model: Model) -> Agent[None, str]:
    return Agent(model, instructions="中文回答。参考提供的对话历史；缺少信息时明确说明。")


def main() -> None:
    agent = build_agent(build_model())
    first = agent.run_sync(FIRST_PROMPT, usage_limits=UsageLimits(request_limit=3))
    print("第一轮：", first.output)
    # 用内存中的 JSON 往返展示历史恢复，不把用户对话写入磁盘。
    history = ModelMessagesTypeAdapter.validate_json(first.all_messages_json())
    second = agent.run_sync(
        SECOND_PROMPT, message_history=history,
        usage_limits=UsageLimits(request_limit=3),
    )
    print("第二轮：", second.output)
    print("本轮新增消息：", len(second.new_messages()))
    print("全部消息：", len(second.all_messages()))


if __name__ == "__main__":
    main()

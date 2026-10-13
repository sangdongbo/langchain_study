"""05：显式传递历史，在第二轮修改第一轮的采购数量。"""

# ModelMessagesTypeAdapter 把 JSON 历史恢复为框架消息对象，保留消息与工具片段的类型。
from pydantic_ai import Agent
from pydantic_ai.messages import ModelMessagesTypeAdapter
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

# 模型配置集中在共享包中，各轮对话只负责传入用户输入与历史。
from pydantic_examples.config import build_model

# 第二轮故意省略单价：模型必须通过第一轮历史才能获得完整计算条件。
FIRST_PROMPT = "记住本次采购：4 台 AI 推理服务器，每台 68000 元。请确认数量和单价。"
SECOND_PROMPT = "数量改成 6 台，单价不变，现在总价是多少？"


def build_agent(model: Model) -> Agent[None, str]:
    # 复用同一个 Agent 不会自动保存本例的会话；历史需要在每次运行时显式传入。
    return Agent(model, instructions="中文回答。参考提供的对话历史；缺少信息时明确说明。")


def main() -> None:
    agent = build_agent(build_model())
    # 第一轮不传历史，从新会话开始；这里的请求上限仅作用于这一轮。
    first = agent.run_sync(FIRST_PROMPT, usage_limits=UsageLimits(request_limit=3))
    print("第一轮：", first.output)
    # all_messages_json 返回 JSON bytes；这里只在内存中往返，展示历史可被序列化和恢复。
    history = ModelMessagesTypeAdapter.validate_json(first.all_messages_json())
    # message_history 保留第一轮上下文；不要把历史重新拼成一条普通用户消息。
    second = agent.run_sync(
        SECOND_PROMPT, message_history=history,
        usage_limits=UsageLimits(request_limit=3),
    )
    # 408000 元在本课由模型回答；要由程序保证计算准确，可结合第 03 课的工具。
    print("第二轮：", second.output)
    # new_messages 只含第二轮新增内容；all_messages 还包含传入的第一轮历史。
    print("本轮新增消息：", len(second.new_messages()))
    print("全部消息：", len(second.all_messages()))


# 独立运行时演示两轮真实对话；导入时不会读取 .env 或发出请求。
if __name__ == "__main__":
    main()

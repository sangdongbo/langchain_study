"""验证历史 JSON 往返、第二轮上下文和独立会话。"""

# UserPromptPart 用于检查用户输入；TypeAdapter 用于验证历史序列化后的恢复结果。
from pydantic_ai import models
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

# 复用两轮实际提示和 Agent 配置，替换模型后仍执行框架的历史传递逻辑。
from run import FIRST_PROMPT, SECOND_PROMPT, build_agent

# 禁止真实请求，让「有历史 / 无历史」的对比完全由本地消息决定。
models.ALLOW_MODEL_REQUESTS = False


def respond(messages, info):
    # 只检查实际传给模型的用户片段，不利用 Agent 对象或测试外部变量保存会话。
    prompts = [p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)]
    if prompts[-1] == FIRST_PROMPT:
        answer = "已记录 4 台，每台 68000 元。"
    elif FIRST_PROMPT in prompts:
        # 第二轮看到第一轮输入时返回已知单价下的总额，验证上下文确实到达模型。
        answer = "6 × 68000 = 408000 元。"
    else:
        # 只给第二轮输入时缺少单价，模拟明确说明信息不足的回答。
        answer = "缺少单价信息。"
    return ModelResponse(parts=[TextPart(answer)])


def main() -> None:
    agent = build_agent(FunctionModel(respond))
    first = agent.run_sync(FIRST_PROMPT)
    # JSON bytes 往返后，消息对象应与原来的完整历史相同。
    history = ModelMessagesTypeAdapter.validate_json(first.all_messages_json())
    assert history == first.all_messages()
    second = agent.run_sync(SECOND_PROMPT, message_history=history)
    # 第二轮完整历史保留第一轮前缀，长度由原历史加本轮新增消息组成。
    assert "408000" in second.output
    assert second.all_messages()[:len(history)] == history
    assert len(second.all_messages()) == len(history) + len(second.new_messages())
    # 再复用相同 Agent，但不传历史：必须是新会话，不能泄漏上次采购的单价。
    assert agent.run_sync(SECOND_PROMPT).output == "缺少单价信息。"
    print("05 PASS：历史序列化、多轮上下文、独立会话")


# 直接运行即可演示历史恢复与会话隔离，不保存文件或访问数据库。
if __name__ == "__main__":
    main()

"""验证历史 JSON 往返、第二轮上下文和独立会话。"""

from pydantic_ai import models
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel

from run import FIRST_PROMPT, SECOND_PROMPT, build_agent

models.ALLOW_MODEL_REQUESTS = False


def respond(messages, info):
    prompts = [p.content for m in messages for p in m.parts if isinstance(p, UserPromptPart)]
    if prompts[-1] == FIRST_PROMPT:
        answer = "已记录 4 台，每台 68000 元。"
    elif FIRST_PROMPT in prompts:
        answer = "6 × 68000 = 408000 元。"
    else:
        answer = "缺少单价信息。"
    return ModelResponse(parts=[TextPart(answer)])


def main() -> None:
    agent = build_agent(FunctionModel(respond))
    first = agent.run_sync(FIRST_PROMPT)
    history = ModelMessagesTypeAdapter.validate_json(first.all_messages_json())
    assert history == first.all_messages()
    second = agent.run_sync(SECOND_PROMPT, message_history=history)
    assert "408000" in second.output
    assert second.all_messages()[:len(history)] == history
    assert len(second.all_messages()) == len(history) + len(second.new_messages())
    assert agent.run_sync(SECOND_PROMPT).output == "缺少单价信息。"
    print("05 PASS：历史序列化、多轮上下文、独立会话")


if __name__ == "__main__":
    main()

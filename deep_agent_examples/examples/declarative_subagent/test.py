"""声明式 SubAgent 离线测试，不需要模型 API Key。

运行命令：
    uv run python examples/declarative_subagent/test.py

预期结果：
    输出“声明式 SubAgent 离线测试通过”，并验证 isolated/fork 的消息隔离和 State 回传。
"""

from __future__ import annotations

import os
from typing import NotRequired

# 测试只使用脚本化模型，不上传 LangSmith trace。
os.environ["LANGSMITH_TRACING"] = "false"

from deepagents import SubAgent, create_deep_agent  # noqa: E402
from deepagents.graph import DeepAgentState  # noqa: E402
from langchain.agents.middleware import AgentMiddleware  # noqa: E402
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage  # noqa: E402

from deep_agent_examples.testing import (  # noqa: E402
    ToolCapableFakeModel,
    configure_utf8_output,
)


# 父子共享的公开 State 字段，用来观察子 Agent 的回写结果。
class SharedState(DeepAgentState):
    request_id: NotRequired[str]
    child_note: NotRequired[str]


class ChildNoteMiddleware(AgentMiddleware):
    state_schema = SharedState

    def after_agent(self, state, runtime):  # noqa: ARG002
        # 子 Agent 结束时记录它是否读到了父 State 的 request_id。
        return {"child_note": f"child-saw:{state.get('request_id')}"}


def _task_call(mode: str) -> AIMessage:
    # 父 Fake Model 首轮固定委派给 risk-reviewer。
    return AIMessage(
        # 空文本表示本轮只请求 task 工具，不直接输出最终回答。
        content="",
        tool_calls=[
            {
                # task 是 create_deep_agent 为 subagents 自动注册的委派工具。
                "name": "task",
                "args": {
                    # description 是子 Agent 在 isolated 模式下收到的任务文本。
                    "description": "Inspect delegated inventory risk only.",
                    # subagent_type 必须等于子配置中的 name。
                    "subagent_type": "risk-reviewer",
                },
                # id 把返回的 ToolMessage 与本次委派关联起来。
                "id": f"task-{mode}",
            }
        ],
    )


def run_case(mode: str) -> tuple[dict, ToolCapableFakeModel]:
    # 子模型只返回报告；父模型先发 task，再基于 ToolMessage 汇总。
    child_model = ToolCapableFakeModel(
        responses=[AIMessage(content=f"{mode} child report")]
    )
    parent_model = ToolCapableFakeModel(
        responses=[_task_call(mode), AIMessage(content=f"{mode} parent report")]
    )
    child: SubAgent = {
        # name：父模型通过 task.subagent_type 使用的路由名。
        "name": "risk-reviewer",
        # description：给父模型看的能力说明；Fake Model 场景仍保持真实结构。
        "description": "Deterministic child for propagation tests.",
        # model：只运行子 Agent 的脚本化模型。
        "model": child_model,
        # tools：空列表表示子 Agent 不允许调用任何业务工具。
        "tools": [],
        # middleware：子 Agent 结束时把 child_note 写回共享 State。
        "middleware": [ChildNoteMiddleware()],
        # mode：isolated 隔离父消息，fork 复制父对话；公开 State 都可传播。
        "mode": mode,
        # system_prompt：子 Agent 自己的系统提示，不影响父模型。
        "system_prompt": "Return the delegated result.",
    }
    parent = create_deep_agent(
        # model：先生成 task 调用，再消费子结果给出最终回复。
        model=parent_model,
        # subagents：注册 child 后框架自动提供 task 工具。
        subagents=[child],
        # state_schema：声明 request_id/child_note 可以在父子 State 中合并。
        state_schema=SharedState,
        # 父测试 Graph 的名称。
        name=f"{mode}-parent-test",
    )
    result = parent.invoke(
        {
            "messages": [
                {
                    "role": "user",
                    "content": "PARENT_SECRET_CONTEXT: review this request.",
                }
            ],
            "request_id": f"request-{mode}",
        }
    )
    return result, child_model


def _message_texts(model: ToolCapableFakeModel) -> list[str]:
    return [
        str(message.content)
        for message in model.seen_messages[0]
        if isinstance(message, HumanMessage)
    ]


def main() -> None:
    configure_utf8_output()
    isolated, isolated_child = run_case("isolated")
    forked, forked_child = run_case("fork")

    isolated_text = "\n".join(_message_texts(isolated_child))
    forked_text = "\n".join(_message_texts(forked_child))

    # isolated 只能看到委派描述；fork 会继承有效父对话。
    assert "Inspect delegated inventory risk only." in isolated_text
    assert "PARENT_SECRET_CONTEXT" not in isolated_text
    assert "PARENT_SECRET_CONTEXT" in forked_text
    assert isolated["child_note"] == "child-saw:request-isolated"
    assert forked["child_note"] == "child-saw:request-fork"
    # 两种模式都会把子 Agent 最终回复包装为父侧 task ToolMessage。
    assert any(
        isinstance(message, ToolMessage) and message.content == "isolated child report"
        for message in isolated["messages"]
    )
    assert any(
        isinstance(message, ToolMessage) and message.content == "fork child report"
        for message in forked["messages"]
    )

    print("声明式 SubAgent 离线测试通过")
    print("- isolated 只接收委派任务，不接收父对话")
    print("- fork 会接收有效的父对话")
    print("- 两种模式都会把公开的自定义 State 返回给父 Agent")
    print("- 子 Agent 的最终 AIMessage 会成为父任务的 ToolMessage")


if __name__ == "__main__":
    main()

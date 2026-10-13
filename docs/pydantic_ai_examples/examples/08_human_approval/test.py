"""确定性验证审批前不执行、批准、编辑、拒绝和重建 Agent 后恢复。"""

import sys
from unittest.mock import patch

from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolApproved, models
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits

from run import PROMPT, ApprovalDeps, approval_result, build_agent, main as run_demo

models.ALLOW_MODEL_REQUESTS = False


def respond(messages, info):
    if any(isinstance(p, RetryPromptPart) for p in messages[-1].parts):
        return ModelResponse(parts=[TextPart("参数不合法，未发布。")])
    returns = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
    if returns:
        return ModelResponse(parts=[TextPart(str(returns[0].content))])
    return ModelResponse(parts=[ToolCallPart(
        "publish_review", {"department": "研发平台部", "amount_yuan": 272000}, tool_call_id="publish-1",
    )])


def check_entrypoint_stops(model, error_text, published_count) -> None:
    deps = ApprovalDeps()
    with (
        patch("run.build_model", return_value=model),
        patch("run.ApprovalDeps", return_value=deps),
        patch.object(sys, "argv", ["run.py", "--decision", "approve"]),
    ):
        try:
            run_demo()
        except RuntimeError as error:
            assert error_text in str(error)
            print("[预期停止]", error)
        else:
            raise AssertionError("非预期审批流程必须停止。")
    assert len(deps.published) == published_count


def main() -> None:
    for decision, amount in (("approve", 272000), ("edit", 268000), ("reject", None)):
        deps = ApprovalDeps()
        usage = RunUsage()
        limits = UsageLimits(request_limit=4)
        first = build_agent(FunctionModel(respond)).run_sync(PROMPT, deps=deps, usage=usage, usage_limits=limits)
        assert isinstance(first.output, DeferredToolRequests)
        assert deps.published == []
        call = first.output.approvals[0]
        assert call.tool_call_id == "publish-1"
        history = ModelMessagesTypeAdapter.validate_json(first.all_messages_json())
        rebuilt = build_agent(FunctionModel(respond))
        resumed = rebuilt.run_sync(
            message_history=history,
            deferred_tool_results=DeferredToolResults(approvals={call.tool_call_id: approval_result(call, decision)}),
            deps=deps, usage=usage, usage_limits=limits,
        )
        assert isinstance(resumed.output, str)
        assert deps.published == ([] if amount is None else [{"department": "研发平台部", "amount_yuan": amount}])
        assert resumed.usage.requests == 2
        if decision == "reject":
            assert "人工拒绝" in resumed.output
        else:
            assert f"{amount} 元" in resumed.output
    try:
        approval_result(call, "unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("未知决策必须被拒绝。")

    for limit, approval in (
        (4, ToolApproved(override_args={"department": "研发平台部", "amount_yuan": -1})),
        (1, ToolApproved()),
    ):
        deps, usage = ApprovalDeps(), RunUsage()
        agent = build_agent(FunctionModel(respond))
        limits = UsageLimits(request_limit=limit)
        first = agent.run_sync(PROMPT, deps=deps, usage=usage, usage_limits=limits)
        assert isinstance(first.output, DeferredToolRequests)
        call = first.output.approvals[0]
        try:
            resumed = agent.run_sync(
                message_history=first.all_messages(),
                deferred_tool_results=DeferredToolResults(approvals={call.tool_call_id: approval}),
                deps=deps, usage=usage, usage_limits=limits,
            )
        except UsageLimitExceeded:
            assert limit == 1
            assert deps.published == [{"department": "研发平台部", "amount_yuan": 272000}]
            print("[边界已验证] 工具已经执行，后续汇总请求被上限阻止；不能假设未发布。")
        else:
            assert limit == 4
            assert deps.published == []
            assert any(isinstance(p, RetryPromptPart) for m in resumed.all_messages() for p in m.parts)
            print("[已阻止] 人工修改后的负数金额未通过校验，零发布。")
        assert usage.requests <= limit

    check_entrypoint_stops(
        FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("未提出发布请求。")])),
        "未进入审批流程", 0,
    )
    calls = [ToolCallPart(
        "publish_review", {"department": "研发平台部", "amount_yuan": 272000}, tool_call_id=f"publish-{i}",
    ) for i in (1, 2)]
    check_entrypoint_stops(
        FunctionModel(lambda messages, info: ModelResponse(parts=calls)), "只审批单笔", 0,
    )

    def request_again(messages, info):
        if any(isinstance(p, ToolReturnPart) for p in messages[-1].parts):
            return ModelResponse(parts=[calls[1]])
        return respond(messages, info)

    check_entrypoint_stops(
        FunctionModel(request_again),
        "需再次人工确认", 1,
    )
    print("08 PASS：审批路径、重建恢复、参数校验、共享上限与入口停止边界")


if __name__ == "__main__":
    main()

"""验证实际委派、子 Agent 结果和父子共享请求上限。"""

from pydantic_ai import models
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

from run import BudgetReview, ReviewFacts, build_agents

models.ALLOW_MODEL_REQUESTS = False


def parent_response(messages, info):
    returns = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
    if returns:
        assert isinstance(returns[0].content, BudgetReview)
        assert returns[0].content.gap_yuan == 4000
        return ModelResponse(parts=[TextPart("预算专家确认缺口 4000 元。")])
    return ModelResponse(parts=[ToolCallPart("delegate_budget_review", {})])


def make_parent():
    parent, _ = build_agents(
        FunctionModel(parent_response),
        TestModel(custom_output_args={"gap_yuan": 4000, "reason": "总额超过预算。"}),
    )
    return parent


def main() -> None:
    print("\n场景 1：父子共享 3 次模型请求预算，完成委派与汇总。", flush=True)
    result = make_parent().run_sync("委派预算审查", deps=ReviewFacts(), usage_limits=UsageLimits(request_limit=3))
    assert "4000" in result.output
    assert result.usage.requests == 3
    assert result.usage.tool_calls >= 1
    print("[父 Agent 汇总]", result.output, flush=True)
    print("父子合计请求数：", result.usage.requests, flush=True)
    print("\n场景 2：预算仅 2 次请求，阻止第三次父级汇总请求。", flush=True)
    try:
        make_parent().run_sync("委派预算审查", deps=ReviewFacts(), usage_limits=UsageLimits(request_limit=2))
    except UsageLimitExceeded:
        print("[已阻止] UsageLimitExceeded：子 Agent 请求计入同一预算。", flush=True)
    else:
        raise AssertionError("子 Agent 的请求也必须计入父级上限。")
    print("07 PASS：真实父子委派、类型化结果、共享预算")


if __name__ == "__main__":
    main()

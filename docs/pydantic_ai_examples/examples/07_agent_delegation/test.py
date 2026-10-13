"""验证实际委派、子 Agent 结果和父子共享请求上限。"""

# 父模型由函数脚本控制工具调用；子模型用 TestModel 提交固定的类型化预算结果。
from pydantic_ai import models
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel
from pydantic_ai.usage import UsageLimits

# 使用真实父子 Agent 和真实委派工具，测试只替换两级模型。
from run import BudgetReview, ReviewFacts, build_agents

# 两级 Agent 都禁止发出真实模型请求。
models.ALLOW_MODEL_REQUESTS = False


def parent_response(messages, info):
    # 父级收到工具返回后才汇总，第一轮则要求执行实际的委派工具。
    returns = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
    if returns:
        # 直接验证父级取得校验后的 BudgetReview，防止委派只返回未检查的自然语言。
        assert isinstance(returns[0].content, BudgetReview)
        assert returns[0].content.gap_yuan == 4000
        return ModelResponse(parts=[TextPart("预算专家确认缺口 4000 元。")])
    return ModelResponse(parts=[ToolCallPart("delegate_budget_review", {})])


def make_parent():
    # 每个场景重新构造父子 Agent，避免上一个测试的状态影响请求上限检查。
    parent, _ = build_agents(
        FunctionModel(parent_response),
        TestModel(custom_output_args={"gap_yuan": 4000, "reason": "总额超过预算。"}),
    )
    return parent


def main() -> None:
    # 3 次请求分别是父提出调用、子提交结果、父汇总；工具执行次数单独统计。
    print("\n场景 1：父子共享 3 次模型请求预算，完成委派与汇总。", flush=True)
    result = make_parent().run_sync("委派预算审查", deps=ReviewFacts(), usage_limits=UsageLimits(request_limit=3))
    assert "4000" in result.output
    assert result.usage.requests == 3
    assert result.usage.tool_calls >= 1
    print("[父 Agent 汇总]", result.output, flush=True)
    print("父子合计请求数：", result.usage.requests, flush=True)
    # 若子 Agent 没共享 usage，2 次请求上限就可能错误地允许父级汇总通过。
    print("\n场景 2：预算仅 2 次请求，阻止第三次父级汇总请求。", flush=True)
    try:
        make_parent().run_sync("委派预算审查", deps=ReviewFacts(), usage_limits=UsageLimits(request_limit=2))
    except UsageLimitExceeded:
        print("[已阻止] UsageLimitExceeded：子 Agent 请求计入同一预算。", flush=True)
    else:
        raise AssertionError("子 Agent 的请求也必须计入父级上限。")
    print("07 PASS：真实父子委派、类型化结果、共享预算")


# 单独运行即可演示父子共享预算的成功与失败路径。
if __name__ == "__main__":
    main()

"""强制第一次结论错误，验证修正、耗尽及请求预算。"""

from pydantic_ai import models
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

from run import ReviewFacts, build_agent

models.ALLOW_MODEL_REQUESTS = False


def scripted_model(verdicts):
    step = 0

    def respond(messages, info):
        nonlocal step
        verdict = verdicts[min(step, len(verdicts) - 1)]
        step += 1
        return ModelResponse(parts=[ToolCallPart(
            info.output_tools[0].name, {"verdict": verdict, "reason": "根据已知预算评审。"}
        )])

    return FunctionModel(respond)


def main() -> None:
    print("\n场景 1：模型先给出错误结论，再根据校验提示修正。", flush=True)
    result = build_agent(scripted_model(["approve", "reject"])).run_sync("评审", deps=ReviewFacts())
    assert result.output.verdict == "reject"
    assert result.usage.requests == 2
    assert any(isinstance(p, RetryPromptPart) for m in result.all_messages() for p in m.parts)
    print("修正后结果：", result.output.model_dump_json(), flush=True)
    print("\n场景 2：总额等于预算，允许采购。", flush=True)
    within = build_agent(scripted_model(["approve"])).run_sync("评审", deps=ReviewFacts(268000, 268000))
    assert within.output.verdict == "approve"
    for limits, error in ((None, UnexpectedModelBehavior), (UsageLimits(request_limit=1), UsageLimitExceeded)):
        print(f"\n失败场景：预期触发 {error.__name__}。", flush=True)
        try:
            build_agent(scripted_model(["approve"])).run_sync("评审", deps=ReviewFacts(), usage_limits=limits)
        except error:
            print(f"[已阻止] {error.__name__}：持续错误不会无限请求。", flush=True)
        else:
            raise AssertionError("持续错误应耗尽重试或触发请求上限。")
    print("04 PASS：业务修正、预算边界、重试耗尽、请求上限")


if __name__ == "__main__":
    main()

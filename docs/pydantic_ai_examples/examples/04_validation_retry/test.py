"""强制第一次结论错误，验证修正、耗尽及请求预算。"""

# 两种异常分别表示修正次数耗尽和运行用量超限；FunctionModel 让错误可稳定复现。
from pydantic_ai import models
from pydantic_ai.exceptions import UnexpectedModelBehavior, UsageLimitExceeded
from pydantic_ai.messages import ModelResponse, RetryPromptPart, ToolCallPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import UsageLimits

# 复用真实业务 validator，离线模型只控制每次提交的建议。
from run import ReviewFacts, build_agent

# 测试不会请求真实模型，即使仓库已有 .env 密钥。
models.ALLOW_MODEL_REQUESTS = False


def scripted_model(verdicts):
    # 每个测试模型有自己的步骤计数，按传入的结论序列模拟模型响应。
    step = 0

    def respond(messages, info):
        nonlocal step
        # 用完序列后重复最后一个结论，便于模拟模型持续出错直到触发上限。
        verdict = verdicts[min(step, len(verdicts) - 1)]
        step += 1
        # 输出工具名由 Agent 的输出 schema 生成，不把框架内部名称硬编码在测试里。
        return ModelResponse(parts=[ToolCallPart(
            info.output_tools[0].name, {"verdict": verdict, "reason": "根据已知预算评审。"}
        )])

    return FunctionModel(respond)


def main() -> None:
    # 错误 approve → 正确 reject：必须出现两次请求和一条真实修正提示。
    print("\n场景 1：模型先给出错误结论，再根据校验提示修正。", flush=True)
    result = build_agent(scripted_model(["approve", "reject"])).run_sync("评审", deps=ReviewFacts())
    assert result.output.verdict == "reject"
    assert result.usage.requests == 2
    assert any(isinstance(p, RetryPromptPart) for m in result.all_messages() for p in m.parts)
    print("修正后结果：", result.output.model_dump_json(), flush=True)
    print("\n场景 2：总额等于预算，允许采购。", flush=True)
    # 边界金额相等时应允许，而不是误判为超预算。
    within = build_agent(scripted_model(["approve"])).run_sync("评审", deps=ReviewFacts(268000, 268000))
    assert within.output.verdict == "approve"
    # 无额外用量限制时耗尽 retries；仅允许 1 次请求时会更早被 request_limit 阻止。
    for limits, error in ((None, UnexpectedModelBehavior), (UsageLimits(request_limit=1), UsageLimitExceeded)):
        print(f"\n失败场景：预期触发 {error.__name__}。", flush=True)
        try:
            build_agent(scripted_model(["approve"])).run_sync("评审", deps=ReviewFacts(), usage_limits=limits)
        except error:
            print(f"[已阻止] {error.__name__}：持续错误不会无限请求。", flush=True)
        else:
            raise AssertionError("持续错误应耗尽重试或触发请求上限。")
    print("04 PASS：业务修正、预算边界、重试耗尽、请求上限")


# 推荐用这个离线入口演示重试，真实模型首次就答对时不会出现修正过程。
if __name__ == "__main__":
    main()

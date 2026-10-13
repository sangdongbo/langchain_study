"""执行真实工具，验证租户隔离与非法工具参数重试。"""

from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

from run import BUDGETS, PROMPT, PurchaseDeps, build_agent

models.ALLOW_MODEL_REQUESTS = False


def scripted_model(invalid_first=False):
    step = 0

    def respond(messages, info):
        nonlocal step
        step += 1
        if invalid_first and step == 1:
            return ModelResponse(parts=[ToolCallPart("calculate_total", {"quantity": 0, "unit_price_yuan": 68000})])
        current = step - int(invalid_first)
        if current == 1:
            return ModelResponse(parts=[ToolCallPart("calculate_total", {"quantity": 4, "unit_price_yuan": 68000})])
        if current == 2:
            total = next(part.content for part in messages[-1].parts if isinstance(part, ToolReturnPart))
            return ModelResponse(parts=[ToolCallPart("check_budget", {"department": "研发平台部", "amount_yuan": total})])
        return ModelResponse(parts=[TextPart("预算查询完成。")])

    return FunctionModel(respond)


def main() -> None:
    for tenant, gap in (("tenant-a", 4000), ("tenant-b", 0)):
        result = build_agent(scripted_model()).run_sync(PROMPT, deps=PurchaseDeps(tenant, BUDGETS))
        returns = [p for m in result.all_messages() for p in m.parts if isinstance(p, ToolReturnPart)]
        assert returns[0].content == 272000
        assert returns[1].content["gap_yuan"] == gap
    result = build_agent(scripted_model(invalid_first=True)).run_sync(PROMPT, deps=PurchaseDeps("tenant-a", BUDGETS))
    assert any(isinstance(p, RetryPromptPart) for m in result.all_messages() for p in m.parts)
    try:
        build_agent(scripted_model()).run_sync(PROMPT, deps=PurchaseDeps("unknown", BUDGETS))
    except PermissionError:
        pass
    else:
        raise AssertionError("未知租户不应读取预算。")
    print("03 PASS：工具计算、租户隔离、参数校验")


if __name__ == "__main__":
    main()

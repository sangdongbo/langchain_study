"""执行真实工具，验证租户隔离与非法工具参数重试。"""

# 消息片段区分工具请求、工具返回和修正提示；FunctionModel 用本地函数模拟模型响应。
from pydantic_ai import models
from pydantic_ai.messages import ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel

# 工具和租户判断仍执行 run.py 中的真实 Python 函数，只替换模型响应。
from run import BUDGETS, PROMPT, PurchaseDeps, build_agent

# 离线运行不允许请求真实模型；预算数据也只来自内存字典。
models.ALLOW_MODEL_REQUESTS = False


def scripted_model(invalid_first=False):
    # 每次构造都创建独立计数器，避免不同租户或不同场景共享脚本步骤。
    step = 0

    def respond(messages, info):
        # nonlocal 更新外层计数；每次 Agent 向模型请求下一步时执行一次本函数。
        nonlocal step
        step += 1
        if invalid_first and step == 1:
            # 数量为 0 会在工具函数执行前被参数 schema 拒绝，框架产生修正提示。
            return ModelResponse(parts=[ToolCallPart("calculate_total", {"quantity": 0, "unit_price_yuan": 68000})])
        # 若插入过错误请求，将后面的正常步骤编号平移一位。
        current = step - int(invalid_first)
        if current == 1:
            return ModelResponse(parts=[ToolCallPart("calculate_total", {"quantity": 4, "unit_price_yuan": 68000})])
        if current == 2:
            # 从真实工具返回取总额，再请求预算；不在脚本中伪造计算工具的结果。
            total = next(part.content for part in messages[-1].parts if isinstance(part, ToolReturnPart))
            return ModelResponse(parts=[ToolCallPart("check_budget", {"department": "研发平台部", "amount_yuan": total})])
        # 工具调用完成后，用文字结束运行，模拟模型的最后汇总。
        return ModelResponse(parts=[TextPart("预算查询完成。")])

    return FunctionModel(respond)


def main() -> None:
    # 模型参数相同，仅替换可信 deps 中的租户，应获得各自预算和缺口。
    for tenant, gap in (("tenant-a", 4000), ("tenant-b", 0)):
        result = build_agent(scripted_model()).run_sync(PROMPT, deps=PurchaseDeps(tenant, BUDGETS))
        returns = [p for m in result.all_messages() for p in m.parts if isinstance(p, ToolReturnPart)]
        assert returns[0].content == 272000
        assert returns[1].content["gap_yuan"] == gap
    # 强制一次非法参数，确认真实消息历史中留下 RetryPromptPart。
    result = build_agent(scripted_model(invalid_first=True)).run_sync(PROMPT, deps=PurchaseDeps("tenant-a", BUDGETS))
    assert any(isinstance(p, RetryPromptPart) for m in result.all_messages() for p in m.parts)
    # 未知租户属于权限错误，应直接终止，不能让模型通过重试扩大可访问范围。
    try:
        build_agent(scripted_model()).run_sync(PROMPT, deps=PurchaseDeps("unknown", BUDGETS))
    except PermissionError:
        pass
    else:
        raise AssertionError("未知租户不应读取预算。")
    print("03 PASS：工具计算、租户隔离、参数校验")


# 与真实演示分开运行，测试不需要供应商密钥。
if __name__ == "__main__":
    main()

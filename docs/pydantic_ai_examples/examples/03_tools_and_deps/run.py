"""03：让模型调用计算工具和带租户上下文的预算工具。"""

from dataclasses import dataclass
from typing import Annotated

from pydantic import Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from pydantic_examples.config import build_model

PROMPT = "研发平台部买 4 台服务器，每台 68000 元。请先计算总额，再查预算，说明缺口。"
BUDGETS = {"tenant-a": {"研发平台部": 268000}, "tenant-b": {"研发平台部": 900000}}


@dataclass
class PurchaseDeps:
    tenant_id: str
    budgets: dict[str, dict[str, int]]


def build_agent(model: Model) -> Agent[PurchaseDeps, str]:
    agent = Agent(
        model, deps_type=PurchaseDeps,
        instructions="必须先调用 calculate_total，再用所得金额调用 check_budget。中文报告金额与缺口。",
    )

    @agent.tool_plain
    def calculate_total(
        quantity: Annotated[int, Field(gt=0)],
        unit_price_yuan: Annotated[int, Field(gt=0)],
    ) -> int:
        """计算采购总额，单位为整数元。"""
        return quantity * unit_price_yuan

    @agent.tool
    def check_budget(
        ctx: RunContext[PurchaseDeps], department: str,
        amount_yuan: Annotated[int, Field(ge=0)],
    ) -> dict[str, int | bool]:
        """查询当前认证租户中该部门的预算，返回是否足够和缺口。"""
        tenant_budgets = ctx.deps.budgets.get(ctx.deps.tenant_id)
        if tenant_budgets is None:
            raise PermissionError("当前租户没有预算访问权限。")
        if department not in tenant_budgets:
            raise ModelRetry("找不到该部门，请核对输入中的部门名称。")
        budget = tenant_budgets[department]
        return {
            "budget_yuan": budget, "amount_yuan": amount_yuan,
            "enough": amount_yuan <= budget, "gap_yuan": max(0, amount_yuan - budget),
        }

    return agent


def main() -> None:
    result = build_agent(build_model()).run_sync(
        PROMPT, deps=PurchaseDeps("tenant-a", BUDGETS),
        usage_limits=UsageLimits(request_limit=6, tool_calls_limit=4),
    )
    print(result.output)
    for message in result.new_messages():
        for part in message.parts:
            if part.part_kind == "tool-return":
                print("tool:", part.tool_name, "=>", part.content)


if __name__ == "__main__":
    main()

"""03：让模型调用计算工具和带租户上下文的预算工具。"""

# dataclass 承载调用方提供的业务上下文；Annotated 为工具参数附加校验约束。
from dataclasses import dataclass
from typing import Annotated

# RunContext 连接本次运行的依赖和用量；ModelRetry 把可修正错误反馈给模型。
from pydantic import Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

# 模型客户端仍复用共享配置，工具中的业务数据使用本地内存。
from pydantic_examples.config import build_model

PROMPT = "研发平台部买 4 台服务器，每台 68000 元。请先计算总额，再查预算，说明缺口。"
# 相同部门在不同租户中拥有独立预算；本例不连接任何数据库。
BUDGETS = {"tenant-a": {"研发平台部": 268000}, "tenant-b": {"研发平台部": 900000}}


@dataclass
class PurchaseDeps:
    # 租户由可信调用方确定，不作为工具参数交给模型选择。
    tenant_id: str
    budgets: dict[str, dict[str, int]]


def build_agent(model: Model) -> Agent[PurchaseDeps, str]:
    # deps_type 声明依赖类型，实际值由 run_sync 的 deps 参数传入。
    agent = Agent(
        model, deps_type=PurchaseDeps,
        instructions="必须先调用 calculate_total，再用所得金额调用 check_budget。中文报告金额与缺口。",
    )

    # tool_plain 不接收 RunContext；参数类型和 Field 会生成工具 schema 并参与校验。
    @agent.tool_plain
    def calculate_total(
        quantity: Annotated[int, Field(gt=0)],
        unit_price_yuan: Annotated[int, Field(gt=0)],
    ) -> int:
        """计算采购总额，单位为整数元。"""
        # 金额由 Python 计算，模型取得返回值后才能据此查询预算。
        return quantity * unit_price_yuan

    # tool 允许通过 ctx 读取依赖；ctx 本身不会出现在让模型填写的参数中。
    @agent.tool
    def check_budget(
        ctx: RunContext[PurchaseDeps], department: str,
        amount_yuan: Annotated[int, Field(ge=0)],
    ) -> dict[str, int | bool]:
        """查询当前认证租户中该部门的预算，返回是否足够和缺口。"""
        # 先按调用方身份限定数据范围，避免模型越过租户读取其他预算。
        tenant_budgets = ctx.deps.budgets.get(ctx.deps.tenant_id)
        if tenant_budgets is None:
            # 权限问题无法由模型修改参数解决，直接终止，而不是让模型换一个租户。
            raise PermissionError("当前租户没有预算访问权限。")
        if department not in tenant_budgets:
            # 部门名称可能写错，ModelRetry 允许模型核对输入后重新调用工具。
            raise ModelRetry("找不到该部门，请核对输入中的部门名称。")
        budget = tenant_budgets[department]
        # 缺口最小为 0；总额等于预算也视为预算充足。
        return {
            "budget_yuan": budget, "amount_yuan": amount_yuan,
            "enough": amount_yuan <= budget, "gap_yuan": max(0, amount_yuan - budget),
        }

    return agent


def main() -> None:
    # 本例固定认证身份为 tenant-a；正式应用应从服务端认证上下文取得身份。
    result = build_agent(build_model()).run_sync(
        PROMPT, deps=PurchaseDeps("tenant-a", BUDGETS),
        usage_limits=UsageLimits(request_limit=6, tool_calls_limit=4),
    )
    print(result.output)
    # new_messages 是本次运行新增的消息；只筛出工具返回片段，方便核对真实计算结果。
    for message in result.new_messages():
        for part in message.parts:
            if part.part_kind == "tool-return":
                print("tool:", part.tool_name, "=>", part.content)


# 导入本模块不会执行工具或调用真实模型。
if __name__ == "__main__":
    main()

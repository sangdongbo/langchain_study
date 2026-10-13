"""07：父 Agent 通过工具委派给类型化子 Agent，共用请求预算。"""

from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from pydantic_examples.config import build_model


@dataclass
class ReviewFacts:
    total_yuan: int = 272000
    budget_yuan: int = 268000


class BudgetReview(BaseModel):
    gap_yuan: int = Field(ge=0)
    reason: str = Field(min_length=1)


def build_agents(parent_model: Model, child_model: Model):
    child = Agent(child_model, deps_type=ReviewFacts, output_type=BudgetReview, retries=2)

    @child.instructions
    def child_instructions(ctx: RunContext[ReviewFacts]) -> str:
        return f"预算评审：总额 {ctx.deps.total_yuan} 元，预算 {ctx.deps.budget_yuan} 元。计算非负缺口，用中文解释。"

    @child.output_validator
    def validate_gap(ctx: RunContext[ReviewFacts], output: BudgetReview) -> BudgetReview:
        expected = max(0, ctx.deps.total_yuan - ctx.deps.budget_yuan)
        if output.gap_yuan != expected:
            raise ModelRetry(f"缺口应为 {expected} 元，请修正。")
        return output

    parent = Agent(
        parent_model, deps_type=ReviewFacts,
        instructions="必须调用 delegate_budget_review 获取预算专家的结论，再用中文汇总。",
    )

    @parent.tool
    async def delegate_budget_review(ctx: RunContext[ReviewFacts]) -> BudgetReview:
        """委派给预算专家，获取经过业务校验的缺口与理由。"""
        print(
            f"[父 → 子] 委派预算审查：总额 {ctx.deps.total_yuan} 元，预算 {ctx.deps.budget_yuan} 元。",
            flush=True,
        )
        result = await child.run(
            "请按本次事实评审预算。", deps=ctx.deps,
            usage=ctx.usage, usage_limits=ctx.usage_limits,
        )
        print("[子 → 父] 已通过校验的结果：", result.output.model_dump_json(), flush=True)
        print("[父 Agent] 收到工具结果，继续生成汇总。", flush=True)
        return result.output

    return parent, child


def main() -> None:
    model = build_model()
    parent, _ = build_agents(model, model)
    result = parent.run_sync(
        "请委派预算专家评审这项采购并汇总。", deps=ReviewFacts(),
        usage_limits=UsageLimits(request_limit=6, tool_calls_limit=3),
    )
    print("[父 Agent 汇总]", result.output)
    print("父子合计 usage:", result.usage)


if __name__ == "__main__":
    main()

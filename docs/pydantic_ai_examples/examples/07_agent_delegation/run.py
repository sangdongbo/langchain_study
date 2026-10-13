"""07：父 Agent 通过工具委派给类型化子 Agent，共用请求预算。"""

# dataclass 传递父子共用的事实；Pydantic 模型约束子 Agent 的返回结果。
from dataclasses import dataclass

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

# 父子可复用同一客户端，也可以在测试中分别传入不同模型。
from pydantic_examples.config import build_model


@dataclass
class ReviewFacts:
    # 两级 Agent 都读取调用方提供的金额，不各自猜测业务事实。
    total_yuan: int = 272000
    budget_yuan: int = 268000


class BudgetReview(BaseModel):
    # schema 只要求缺口非负；是否等于真实差额还要由下面的业务 validator 检查。
    gap_yuan: int = Field(ge=0)
    reason: str = Field(min_length=1)


def build_agents(parent_model: Model, child_model: Model):
    # 子 Agent 只做预算评审，以类型化对象返回；父 Agent 最后以自然语言汇总。
    child = Agent(child_model, deps_type=ReviewFacts, output_type=BudgetReview, retries=2)

    # 子任务只接收本次业务事实，父级完整对话不会自动传给子级。
    @child.instructions
    def child_instructions(ctx: RunContext[ReviewFacts]) -> str:
        return f"预算评审：总额 {ctx.deps.total_yuan} 元，预算 {ctx.deps.budget_yuan} 元。计算非负缺口，用中文解释。"

    # 验证模型算出的缺口；修正提示仍受重试次数和共用请求上限约束。
    @child.output_validator
    def validate_gap(ctx: RunContext[ReviewFacts], output: BudgetReview) -> BudgetReview:
        expected = max(0, ctx.deps.total_yuan - ctx.deps.budget_yuan)
        if output.gap_yuan != expected:
            raise ModelRetry(f"缺口应为 {expected} 元，请修正。")
        return output

    # 指令要求模型委派，但真正的子 Agent 调用发生在工具函数内部。
    parent = Agent(
        parent_model, deps_type=ReviewFacts,
        instructions="必须调用 delegate_budget_review 获取预算专家的结论，再用中文汇总。",
    )

    # 异步工具可以 await 子任务，父 Agent 等工具返回后再继续下一次模型请求。
    @parent.tool
    async def delegate_budget_review(ctx: RunContext[ReviewFacts]) -> BudgetReview:
        """委派给预算专家，获取经过业务校验的缺口与理由。"""
        print(
            f"[父 → 子] 委派预算审查：总额 {ctx.deps.total_yuan} 元，预算 {ctx.deps.budget_yuan} 元。",
            flush=True,
        )
        # deps 传业务事实；usage 与 usage_limits 传同一用量对象和上限，防止子任务另开预算。
        # 不传 message_history，所以父对话中的用户文本不会自动进入子任务上下文。
        result = await child.run(
            "请按本次事实评审预算。", deps=ctx.deps,
            usage=ctx.usage, usage_limits=ctx.usage_limits,
        )
        # 只有子任务成功且通过业务校验后才打印返回阶段。
        print("[子 → 父] 已通过校验的结果：", result.output.model_dump_json(), flush=True)
        print("[父 Agent] 收到工具结果，继续生成汇总。", flush=True)
        # BudgetReview 作为父级工具结果进入消息，父模型据此生成最后的汇总。
        return result.output

    return parent, child


def main() -> None:
    model = build_model()
    # 同一个模型客户端可以复用；父子角色差异来自 instructions、工具和输出类型。
    parent, _ = build_agents(model, model)
    result = parent.run_sync(
        "请委派预算专家评审这项采购并汇总。", deps=ReviewFacts(),
        usage_limits=UsageLimits(request_limit=6, tool_calls_limit=3),
    )
    # usage 汇总父子请求；本例正常路径通常为父调用工具、子评审、父汇总共 3 次。
    print("[父 Agent 汇总]", result.output)
    print("父子合计 usage:", result.usage)


# 直接运行时才演示真实父子调用，离线测试只复用构造函数。
if __name__ == "__main__":
    main()

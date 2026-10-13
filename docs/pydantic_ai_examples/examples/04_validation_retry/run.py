"""04：校验模型建议与已知业务事实，错误时让模型修正。"""

# dataclass 保存可信事实；Literal 把允许的结论限制为两个固定字符串。
from dataclasses import dataclass
from typing import Literal

# BaseModel 负责字段校验；output_validator 负责字段类型之外的业务判断。
from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

# 离线测试仅复用 build_agent，真实入口才需要 build_model 加载配置。
from pydantic_examples.config import build_model


@dataclass
class ReviewFacts:
    # 事实由调用方提供，模型只提出建议；本例假定调用方已核实这些金额。
    total_yuan: int = 272000
    budget_yuan: int = 268000


class Recommendation(BaseModel):
    # Literal 校验只能排除非法词值，不能判断 approve 是否符合本次预算。
    verdict: Literal["approve", "reject"]
    reason: str = Field(min_length=1)


def build_agent(model: Model) -> Agent[ReviewFacts, Recommendation]:
    # 输出修正最多重试 2 次；main 中另有整个运行的请求次数上限。
    agent = Agent(model, deps_type=ReviewFacts, output_type=Recommendation, retries=2)

    # 动态 instructions 每次运行读取本次 deps，避免把不同采购的事实写死在 Agent 中。
    @agent.instructions
    def policy(ctx: RunContext[ReviewFacts]) -> str:
        return (
            f"中文评审采购：总额 {ctx.deps.total_yuan} 元，预算 {ctx.deps.budget_yuan} 元。"
            "超过预算必须 reject，否则 approve。给出理由。"
        )

    # 字段校验成功后、接受最终输出前，还要检查结论是否符合可信事实。
    @agent.output_validator
    def validate_decision(ctx: RunContext[ReviewFacts], output: Recommendation) -> Recommendation:
        expected = "reject" if ctx.deps.total_yuan > ctx.deps.budget_yuan else "approve"
        print(f"[校验] 模型结论={output.verdict}，预算规则要求={expected}", flush=True)
        if output.verdict != expected:
            # 抛出 ModelRetry 才会触发框架修正流程；剩余上限不足时不会继续请求模型。
            print("[需修正] 结论冲突，提交 ModelRetry；是否重试由剩余上限决定。", flush=True)
            raise ModelRetry(f"结论与预算事实冲突，应为 {expected}。请修正并解释。")
        print("[通过] 结论与预算事实一致，接受本次输出。", flush=True)
        # 返回校验后的对象；这里只验证 verdict，不保证 reason 中每句话都真实。
        return output

    return agent


def main() -> None:
    # 提示模型和校验模型使用同一份事实，避免两处金额不一致。
    facts = ReviewFacts()
    print(f"业务事实：总额 {facts.total_yuan} 元，预算 {facts.budget_yuan} 元。", flush=True)
    result = build_agent(build_model()).run_sync(
        "请给出采购结论。", deps=facts,
        usage_limits=UsageLimits(request_limit=4),
    )
    # 真实模型可能首次就答对；想稳定演示错误修正可运行同目录 test.py。
    print(result.output.model_dump_json(indent=2))
    print("usage:", result.usage)


# 直接运行本文件才发出真实模型请求。
if __name__ == "__main__":
    main()

"""04：校验模型建议与已知业务事实，错误时让模型修正。"""

from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model
from pydantic_ai.usage import UsageLimits

from pydantic_examples.config import build_model


@dataclass
class ReviewFacts:
    total_yuan: int = 272000
    budget_yuan: int = 268000


class Recommendation(BaseModel):
    verdict: Literal["approve", "reject"]
    reason: str = Field(min_length=1)


def build_agent(model: Model) -> Agent[ReviewFacts, Recommendation]:
    agent = Agent(model, deps_type=ReviewFacts, output_type=Recommendation, retries=2)

    @agent.instructions
    def policy(ctx: RunContext[ReviewFacts]) -> str:
        return (
            f"中文评审采购：总额 {ctx.deps.total_yuan} 元，预算 {ctx.deps.budget_yuan} 元。"
            "超过预算必须 reject，否则 approve。给出理由。"
        )

    @agent.output_validator
    def validate_decision(ctx: RunContext[ReviewFacts], output: Recommendation) -> Recommendation:
        expected = "reject" if ctx.deps.total_yuan > ctx.deps.budget_yuan else "approve"
        print(f"[校验] 模型结论={output.verdict}，预算规则要求={expected}", flush=True)
        if output.verdict != expected:
            print("[需修正] 结论冲突，提交 ModelRetry；是否重试由剩余上限决定。", flush=True)
            raise ModelRetry(f"结论与预算事实冲突，应为 {expected}。请修正并解释。")
        print("[通过] 结论与预算事实一致，接受本次输出。", flush=True)
        return output

    return agent


def main() -> None:
    facts = ReviewFacts()
    print(f"业务事实：总额 {facts.total_yuan} 元，预算 {facts.budget_yuan} 元。", flush=True)
    result = build_agent(build_model()).run_sync(
        "请给出采购结论。", deps=facts,
        usage_limits=UsageLimits(request_limit=4),
    )
    print(result.output.model_dump_json(indent=2))
    print("usage:", result.usage)


if __name__ == "__main__":
    main()

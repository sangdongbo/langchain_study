"""08：发布工具先暂停，人工决定后通过历史和 tool_call_id 恢复。"""

import argparse
from dataclasses import dataclass, field
from typing import Annotated

from pydantic import Field
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, RunContext, ToolApproved, ToolDenied
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

from pydantic_examples.config import build_model

PROMPT = "请调用 publish_review，把研发平台部金额 272000 元的采购评审发布到演示列表。"


@dataclass
class ApprovalDeps:
    published: list[dict[str, str | int]] = field(default_factory=list)


def build_agent(model: Model) -> Agent[ApprovalDeps, str | DeferredToolRequests]:
    agent = Agent(
        model, deps_type=ApprovalDeps, output_type=[str, DeferredToolRequests],
        instructions=(
            "单笔发布只提出一次 publish_review 调用，并等待工具结果再报告。"
            "人工可能修改参数；以工具返回的人工批准参数为准报告结果，不把人工修改误报为发布错误。"
            "如果人工拒绝，不再尝试发布，说明已取消。"
        ),
    )

    @agent.tool(requires_approval=True)
    def publish_review(
        ctx: RunContext[ApprovalDeps], department: Annotated[str, Field(min_length=1)],
        amount_yuan: Annotated[int, Field(gt=0)],
    ) -> str:
        """把已审核采购结果发布到当前进程的演示列表，不写外部系统。"""
        ctx.deps.published.append({"department": department, "amount_yuan": amount_yuan})
        return f"演示发布完成（按人工批准参数）：{department}，{amount_yuan} 元。"

    return agent


def approval_result(call: ToolCallPart, decision: str) -> ToolApproved | ToolDenied:
    if decision == "approve":
        return ToolApproved()
    if decision == "reject":
        return ToolDenied("人工拒绝发布，请结束本次操作。")
    if decision == "edit":
        return ToolApproved(override_args=call.args_as_dict() | {"amount_yuan": 268000})
    raise ValueError("决策只接受 approve、reject 或 edit。")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", choices=["approve", "reject", "edit"])
    args = parser.parse_args()
    agent = build_agent(build_model())
    deps = ApprovalDeps()
    usage = RunUsage()
    limits = UsageLimits(request_limit=6, tool_calls_limit=3)
    first = agent.run_sync(PROMPT, deps=deps, usage=usage, usage_limits=limits)
    if not isinstance(first.output, DeferredToolRequests):
        print(first.output)
        raise RuntimeError("模型没有请求发布工具，未进入审批流程。")
    if len(first.output.approvals) != 1 or first.output.calls:
        raise RuntimeError("本例只审批单笔发布；请求数量或类型不符，停止且不执行。")
    print("暂停时已发布记录数：", len(deps.published))
    call = first.output.approvals[0]
    print("待审批：", call.tool_call_id, call.tool_name, call.args_as_dict())
    decision = args.decision or input("approve / reject / edit（改为 268000 元）：").strip()
    decisions = {call.tool_call_id: approval_result(call, decision)}
    resumed = agent.run_sync(
        message_history=first.all_messages(),
        deferred_tool_results=DeferredToolResults(approvals=decisions),
        deps=deps, usage=usage, usage_limits=limits,
    )
    if isinstance(resumed.output, DeferredToolRequests):
        raise RuntimeError("模型又提出待审批操作；本例停止，需再次人工确认。")
    print(resumed.output)
    print("演示列表：", deps.published)
    print("两阶段合计 usage:", resumed.usage)


if __name__ == "__main__":
    main()

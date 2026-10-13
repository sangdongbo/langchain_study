"""08：发布工具先暂停，人工决定后通过历史和 tool_call_id 恢复。"""

# argparse 支持预选审批决策；dataclass 保存当前进程的演示发布记录。
import argparse
from dataclasses import dataclass, field
from typing import Annotated

# DeferredToolRequests 表示暂停待审批，DeferredToolResults 携带人工决定来恢复运行。
# ToolApproved / ToolDenied 是框架认可的审批结果，不是一条普通的「同意」消息。
from pydantic import Field
from pydantic_ai import Agent, DeferredToolRequests, DeferredToolResults, RunContext, ToolApproved, ToolDenied
from pydantic_ai.messages import ToolCallPart
from pydantic_ai.models import Model
from pydantic_ai.usage import RunUsage, UsageLimits

# 模型沿用共享配置；发布目标仅为内存列表，没有外部采购接口。
from pydantic_examples.config import build_model

PROMPT = "请调用 publish_review，把研发平台部金额 272000 元的采购评审发布到演示列表。"


@dataclass
class ApprovalDeps:
    # default_factory 为每个会话创建新列表，避免多个实例共享同一份可变记录。
    published: list[dict[str, str | int]] = field(default_factory=list)


def build_agent(model: Model) -> Agent[ApprovalDeps, str | DeferredToolRequests]:
    # 输出联合类型使一次运行既能返回普通回答，也能以待审批请求暂停。
    agent = Agent(
        model, deps_type=ApprovalDeps, output_type=[str, DeferredToolRequests],
        instructions=(
            "单笔发布只提出一次 publish_review 调用，并等待工具结果再报告。"
            "人工可能修改参数；以工具返回的人工批准参数为准报告结果，不把人工修改误报为发布错误。"
            "如果人工拒绝，不再尝试发布，说明已取消。"
        ),
    )

    # 提出该工具调用时先暂停；没有人工批准，框架不会执行工具函数体。
    @agent.tool(requires_approval=True)
    def publish_review(
        ctx: RunContext[ApprovalDeps], department: Annotated[str, Field(min_length=1)],
        amount_yuan: Annotated[int, Field(gt=0)],
    ) -> str:
        """把已审核采购结果发布到当前进程的演示列表，不写外部系统。"""
        # 真正的发布动作只在这里发生；原始参数及人工修改后的参数都会经过框架校验。
        ctx.deps.published.append({"department": department, "amount_yuan": amount_yuan})
        return f"演示发布完成（按人工批准参数）：{department}，{amount_yuan} 元。"

    return agent


def approval_result(call: ToolCallPart, decision: str) -> ToolApproved | ToolDenied:
    # 把终端选择转成框架审批对象，恢复时再按原始 tool_call_id 对应到具体调用。
    if decision == "approve":
        # 不传 override_args 表示按模型最初提出的参数执行。
        return ToolApproved()
    if decision == "reject":
        # 拒绝消息交给模型说明取消，工具函数体不执行。
        return ToolDenied("人工拒绝发布，请结束本次操作。")
    if decision == "edit":
        # 本课固定改为 268000 元；字典合并保留其他参数，右侧金额覆盖原始值。
        return ToolApproved(override_args=call.args_as_dict() | {"amount_yuan": 268000})
    # 非法选择不能隐式变成批准。
    raise ValueError("决策只接受 approve、reject 或 edit。")


def main() -> None:
    # 指定 --decision 便于课堂演示；省略时显示调用参数后等待人工输入。
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--decision", choices=["approve", "reject", "edit"])
    args = parser.parse_args()
    agent = build_agent(build_model())
    deps = ApprovalDeps()
    # 两阶段共用同一份用量，暂停后恢复不会把请求计数清零。
    usage = RunUsage()
    limits = UsageLimits(request_limit=6, tool_calls_limit=3)
    # 第一阶段：让模型提出调用，观察审批暂停；此时发布列表应仍为空。
    first = agent.run_sync(PROMPT, deps=deps, usage=usage, usage_limits=limits)
    if not isinstance(first.output, DeferredToolRequests):
        # 模型可能直接回答而没有提出工具请求，不能把这种情况当作完成了审批演示。
        print(first.output)
        raise RuntimeError("模型没有请求发布工具，未进入审批流程。")
    if len(first.output.approvals) != 1 or first.output.calls:
        # 本课只处理一笔内部待审批调用，避免一次决策放行多个发布动作。
        raise RuntimeError("本例只审批单笔发布；请求数量或类型不符，停止且不执行。")
    print("暂停时已发布记录数：", len(deps.published))
    call = first.output.approvals[0]
    print("待审批：", call.tool_call_id, call.tool_name, call.args_as_dict())
    decision = args.decision or input("approve / reject / edit（改为 268000 元）：").strip()
    # 审批结果必须绑定调用 ID；只给模型追加一条「同意」文本无法恢复该工具。
    decisions = {call.tool_call_id: approval_result(call, decision)}
    # 第二阶段：传完整历史、审批结果和原来的业务依赖，继续执行被暂停的运行。
    # 已批准的工具先执行，再请求模型汇总；后面的模型请求失败不会撤销已经发布的记录。
    resumed = agent.run_sync(
        message_history=first.all_messages(),
        deferred_tool_results=DeferredToolResults(approvals=decisions),
        deps=deps, usage=usage, usage_limits=limits,
    )
    if isinstance(resumed.output, DeferredToolRequests):
        # 新请求需要新的人工决定；上一笔的批准不能自动延续到新请求。
        raise RuntimeError("模型又提出待审批操作；本例停止，需再次人工确认。")
    print(resumed.output)
    # 核对实际列表而不只相信模型措辞；approve / edit / reject 对应原金额 / 新金额 / 空。
    print("演示列表：", deps.published)
    print("两阶段合计 usage:", resumed.usage)


# 入口只用于本进程教学，不包含生产系统的持久化、审批人认证和防重复提交。
if __name__ == "__main__":
    main()

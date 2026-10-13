"""确定性验证审批前不执行、批准、编辑、拒绝和重建 Agent 后恢复。"""

# patch 临时替换真实入口的模型、业务依赖和 argv，以离线方式测试整个终端入口。
import sys
from unittest.mock import patch

# 消息片段用于检查暂停、工具返回和参数修正；UsageLimitExceeded 表示用量上限触发。
from pydantic_ai import DeferredToolRequests, DeferredToolResults, ToolApproved, models
from pydantic_ai.exceptions import UsageLimitExceeded
from pydantic_ai.messages import ModelMessagesTypeAdapter, ModelResponse, RetryPromptPart, TextPart, ToolCallPart, ToolReturnPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.usage import RunUsage, UsageLimits

# 复用真正的发布工具和决策转换函数；run_demo 别名区分真实入口与测试 main。
from run import PROMPT, ApprovalDeps, approval_result, build_agent, main as run_demo

# 所有场景只使用 FunctionModel，额外开关防止误接入真实模型。
models.ALLOW_MODEL_REQUESTS = False


def respond(messages, info):
    # 人工修改后的参数不合法时，框架产生重试片段；脚本直接回答，不再申请发布。
    if any(isinstance(p, RetryPromptPart) for p in messages[-1].parts):
        return ModelResponse(parts=[TextPart("参数不合法，未发布。")])
    returns = [p for p in messages[-1].parts if isinstance(p, ToolReturnPart)]
    if returns:
        # 真实工具结果或拒绝说明到达模型后，模拟最终汇总。
        return ModelResponse(parts=[TextPart(str(returns[0].content))])
    # 第一轮固定申请一笔发布；显式调用 ID 便于验证恢复时的审批映射。
    return ModelResponse(parts=[ToolCallPart(
        "publish_review", {"department": "研发平台部", "amount_yuan": 272000}, tool_call_id="publish-1",
    )])


def check_entrypoint_stops(model, error_text, published_count) -> None:
    # 保存同一份内存依赖，入口退出后还能核对已执行多少笔发布。
    deps = ApprovalDeps()
    # patch 只在 with 内生效：不创建真实模型，且用 argv 避免测试等待键盘输入。
    with (
        patch("run.build_model", return_value=model),
        patch("run.ApprovalDeps", return_value=deps),
        patch.object(sys, "argv", ["run.py", "--decision", "approve"]),
    ):
        try:
            run_demo()
        except RuntimeError as error:
            # 只接受预期的停止原因；其他错误不能被当作通过。
            assert error_text in str(error)
            print("[预期停止]", error)
        else:
            raise AssertionError("非预期审批流程必须停止。")
    # 检查实际副作用，而不是依赖错误文字或模型的「已取消」措辞。
    assert len(deps.published) == published_count


def main() -> None:
    # 三条正常路径共用相同输入，区别仅为人工决策和预期最终金额。
    for decision, amount in (("approve", 272000), ("edit", 268000), ("reject", None)):
        deps = ApprovalDeps()
        usage = RunUsage()
        limits = UsageLimits(request_limit=4)
        first = build_agent(FunctionModel(respond)).run_sync(PROMPT, deps=deps, usage=usage, usage_limits=limits)
        # 暂停之前必须零执行；提出工具调用不等于执行了工具。
        assert isinstance(first.output, DeferredToolRequests)
        assert deps.published == []
        call = first.output.approvals[0]
        assert call.tool_call_id == "publish-1"
        # 将历史序列化再重建 Agent，证明恢复不依赖原 Agent 对象中的隐含状态。
        history = ModelMessagesTypeAdapter.validate_json(first.all_messages_json())
        rebuilt = build_agent(FunctionModel(respond))
        # 保留业务依赖与用量，并按原始 ID 提交决定：历史恢复不等于业务状态自动恢复。
        resumed = rebuilt.run_sync(
            message_history=history,
            deferred_tool_results=DeferredToolResults(approvals={call.tool_call_id: approval_result(call, decision)}),
            deps=deps, usage=usage, usage_limits=limits,
        )
        assert isinstance(resumed.output, str)
        # 批准写原金额、修改写新金额、拒绝零执行；两阶段总计 2 次离线模型请求。
        assert deps.published == ([] if amount is None else [{"department": "研发平台部", "amount_yuan": amount}])
        assert resumed.usage.requests == 2
        if decision == "reject":
            assert "人工拒绝" in resumed.output
        else:
            assert f"{amount} 元" in resumed.output
    # 非法决策应明确报错，不能默认放行。
    try:
        approval_result(call, "unknown")
    except ValueError:
        pass
    else:
        raise AssertionError("未知决策必须被拒绝。")

    # 检查两个边界：修改成负数必须拒绝；批准后可能已执行却没有预算请求最终汇总。
    for limit, approval in (
        (4, ToolApproved(override_args={"department": "研发平台部", "amount_yuan": -1})),
        (1, ToolApproved()),
    ):
        deps, usage = ApprovalDeps(), RunUsage()
        agent = build_agent(FunctionModel(respond))
        limits = UsageLimits(request_limit=limit)
        first = agent.run_sync(PROMPT, deps=deps, usage=usage, usage_limits=limits)
        assert isinstance(first.output, DeferredToolRequests)
        call = first.output.approvals[0]
        try:
            resumed = agent.run_sync(
                message_history=first.all_messages(),
                deferred_tool_results=DeferredToolResults(approvals={call.tool_call_id: approval}),
                deps=deps, usage=usage, usage_limits=limits,
            )
        except UsageLimitExceeded:
            # 已批准工具在汇总请求前执行，因此超限不保证零副作用，不能盲目重试。
            assert limit == 1
            assert deps.published == [{"department": "研发平台部", "amount_yuan": 272000}]
            print("[边界已验证] 工具已经执行，后续汇总请求被上限阻止；不能假设未发布。")
        else:
            # 负数金额由框架重新校验；工具函数未执行，且历史里存在参数修正提示。
            assert limit == 4
            assert deps.published == []
            assert any(isinstance(p, RetryPromptPart) for m in resumed.all_messages() for p in m.parts)
            print("[已阻止] 人工修改后的负数金额未通过校验，零发布。")
        assert usage.requests <= limit

    # 模型只回答、没有提出发布调用：入口必须报告未进入审批，而不是伪造暂停。
    check_entrypoint_stops(
        FunctionModel(lambda messages, info: ModelResponse(parts=[TextPart("未提出发布请求。")])),
        "未进入审批流程", 0,
    )
    # 同一轮提出两笔发布：入口必须整批停止，不能让一次 approve 放行两笔。
    calls = [ToolCallPart(
        "publish_review", {"department": "研发平台部", "amount_yuan": 272000}, tool_call_id=f"publish-{i}",
    ) for i in (1, 2)]
    check_entrypoint_stops(
        FunctionModel(lambda messages, info: ModelResponse(parts=calls)), "只审批单笔", 0,
    )

    def request_again(messages, info):
        # 首次工具成功后再申请新调用，用来验证上一笔批准不会自动批准下一笔。
        if any(isinstance(p, ToolReturnPart) for p in messages[-1].parts):
            return ModelResponse(parts=[calls[1]])
        return respond(messages, info)

    check_entrypoint_stops(
        FunctionModel(request_again),
        # 只有第一笔已经执行；第二笔停在待审批阶段。
        "需再次人工确认", 1,
    )
    print("08 PASS：审批路径、重建恢复、参数校验、共享上限与入口停止边界")


# 不调用真实模型或数据库；也可以由项目总离线检查脚本启动。
if __name__ == "__main__":
    main()

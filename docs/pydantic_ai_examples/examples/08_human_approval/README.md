# 08 · 人工审批、暂停与恢复

模型提出发布采购评审，Python 先显示工具名、原始参数和 `tool_call_id`，人决定后才执行。
发布工具只向内存列表添加演示记录，因此三种决策都可以放心观察。

```powershell
uv run python examples/08_human_approval/test.py
# 显示参数后在终端输入决策
uv run python examples/08_human_approval/run.py
# 显式选择决策，适合课堂演示
uv run python examples/08_human_approval/run.py --decision approve
uv run python examples/08_human_approval/run.py --decision reject
uv run python examples/08_human_approval/run.py --decision edit
```

`@agent.tool(requires_approval=True)` 声明该工具需批准；
`output_type=[str, DeferredToolRequests]` 让运行可以返回普通回答或待审批请求。
首次结果为 `DeferredToolRequests` 时，工具函数体尚未执行，列表仍为空。
本例只审批一笔发布；模型在第一阶段请求多次发布时，入口拒绝整批请求，不执行任何一笔。

恢复调用同时传 `message_history=first.all_messages()` 和
`deferred_tool_results=DeferredToolResults(approvals={tool_call_id: decision})`。
决定必须对应原始调用 ID，不要把「同意」只写成一条普通用户消息。

| 决策 | 传给框架的值 | 演示结果 |
| --- | --- | --- |
| approve | `ToolApproved()` | 工具执行，列表记录 272000 元 |
| edit | `ToolApproved(override_args=...)` | 保留部门，金额改为 268000 元后执行 |
| reject | `ToolDenied(...)` | 工具不执行，模型收到拒绝信息 |

演示明确把 edit 固定为 268000 元，便于对照结果。工具参数仍由 PydanticAI 校验，未知
决策由程序拒绝。两阶段共用 `RunUsage` 与 `UsageLimits`，恢复不重置请求预算。
如果模型恢复后又提出需审批的操作，示例停止，不自动批准新增请求。

`override_args` 修改实际执行参数，历史中仍能看到模型最初提出的金额。工具返回明确说明
按人工批准参数执行，Agent 的 instructions 要求按实际金额汇总，避免把人工修改误报为
发布错误。最终核对终端的「演示列表」：edit 应只有一条 268000 元记录。

离线测试覆盖三种路径，并把历史序列化后重建 Agent 再恢复，证明恢复依靠历史与调用 ID。
还检查修改后的非法参数不执行、两阶段共用请求上限、未提出工具请求、多个请求以及
恢复后的新增请求不会自动批准。

批准的工具在恢复阶段先执行，随后模型才汇总。汇总请求超时或被用量上限阻止时，已经
执行的工具不会自动回滚；测试使用 1 次请求预算展示「记录已产生但汇总失败」的边界。
错误退出不能被当作「工具一定没执行」，尤其不能在真实系统中盲目重试提交。

这不是持久化工作流：本例没有保存业务依赖、审批身份、请求预算或执行幂等记录。
真实系统还需验证审批人权限、按会话保存状态，并防止重复恢复造成重复提交。

与 Deep Agents 的 HITL 相比，这里使用 PydanticAI 的 deferred tools，不能传 LangGraph
的 `Command(resume=...)`。本课也没有连接任何采购接口或数据库。

返回：[学习总览](../../README.md)。

# 08 · 人工审批、暂停与恢复

## 为什么仅靠“请先询问我”还不够

模型提出发布采购评审，Python 先显示工具名、原始参数和 `tool_call_id`，人决定后才执行。
发布工具只向内存列表添加演示记录，因此三种决策都可以放心观察。

提示词要求先确认，只能引导模型行为。这里用框架的 `requires_approval=True` 在工具
执行前暂停，程序取得待审批请求并收集人的决定，再显式恢复，执行边界由代码控制。
这种在人参与后继续的方式常叫 Human in the Loop，简称 HITL。

## 先认识暂停和恢复用到的对象

| 名称 | 含义 | 本课在哪里用 |
| --- | --- | --- |
| `ApprovalDeps` | 当前任务的业务依赖，保存演示发布列表 | 两阶段传入同一个 `deps` |
| `DeferredToolRequests` | 框架返回的待处理工具请求 | 第一阶段 `first.output`，从 `approvals` 取得调用 |
| `tool_call_id` | 这一次工具调用的标识 | 将人的决定对应到准确的待审批调用 |
| `ToolApproved` / `ToolDenied` | 批准或拒绝的决定对象 | `approval_result()` 根据终端输入构造 |
| `DeferredToolResults` | 交回框架的待处理工具结果容器 | 本课用其中的 `approvals` 携带审批决定 |

`output_type=[str, DeferredToolRequests]` 允许结果有两种形态：完成时给普通文字，
暂停时给待审批对象。因此先用 `isinstance` 判断 `first.output`，不能总把它当字符串。
“返回了待审批对象”只表示模型提出了操作，不表示发布函数已经执行。

## 对照 run.py 看两个阶段

1. `main()` 创建 Agent、空的演示列表、共享用量和上限，开始第一阶段运行。
2. 模型提出 `publish_review` 调用；框架在函数体执行前暂停。
3. 程序检查只有一笔内部待审批请求，展示 ID、工具名和参数，此时已发布记录数应为 0。
4. 人选择批准、拒绝或修改；`approval_result()` 将字符串选择转换成框架决定对象。
5. 第二阶段交回第一阶段历史、按 ID 关联的决定、原有依赖与用量。
6. 批准时执行工具，拒绝时不执行；框架把结果交给模型汇总，程序最后打印实际列表。

`approve`、`reject`、`edit` 是本教程定义的终端选项。框架实际接收的是决定对象，
所以只在聊天中再写一句“同意”，不能替代第 5 步的恢复参数。

## 怎样运行

```powershell
uv run python examples/08_human_approval/test.py
# 显示参数后在终端输入决策
uv run python examples/08_human_approval/run.py
# 显式选择决策，适合课堂演示
uv run python examples/08_human_approval/run.py --decision approve
uv run python examples/08_human_approval/run.py --decision reject
uv run python examples/08_human_approval/run.py --decision edit
```

在 PyCharm 中省略 `--decision` 时，需要到下方 Run 控制台输入选择并按 Enter。
程序停在输入提示处是在等人工决定；也可以在 Script parameters 填入 `--decision edit`
预选路径。`test.py` 不等待输入，会自动验证各个场景。

## 代码如何绑定批准决定

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

## 最终结果怎么看

正常演示先出现 `暂停时已发布记录数：0` 和待审批详情。批准后列表有一笔 `272000`
元记录，修改后有一笔 `268000` 元记录，拒绝后为空；每次独立运行脚本都会从新的
内存列表开始。程序中的 `override_args` 是覆盖执行参数，不是让模型自己决定怎样改。

查看「演示列表」来确认实际执行结果，不能只相信模型说“已发布”。离线测试中的
`[已阻止]` 和 `[预期停止]` 是保护边界的场景，最后出现 `08 PASS` 才表示检查通过。

如果真实模型没有提出发布请求，程序会明确报“未进入审批流程”；如果恢复后提出新
请求，也会停止等待新的人工确认。这些情况下不能把异常退出说成完整审批成功。

与 Deep Agents 的 HITL 相比，这里使用 PydanticAI 的 deferred tools，不能传 LangGraph
的 `Command(resume=...)`。本课也没有连接任何采购接口或数据库。

上一课：[07 · Agent 委派](../07_agent_delegation/README.md)。
返回：[学习总览](../../README.md)。

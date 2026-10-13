# 07 · Agent 委派与共享预算

父 Agent 负责沟通与汇总，预算专家负责返回 `BudgetReview`。父 Agent 把子 Agent 包装
成一个普通异步工具，模型调用这个工具时，Python 执行 `await child.run(...)`。

```powershell
uv run python examples/07_agent_delegation/test.py
uv run python examples/07_agent_delegation/run.py
```

调用关系：用户 → 父模型 → `delegate_budget_review` → 子模型 → 类型化预算结论 →
父模型汇总。子 Agent 的 validator 复用第 04 课的思路，检查缺口确实为 `4000 元`。

终端在实际调用发生时输出以下阶段，真实演示和离线测试共用相同的委派工具：

```text
[父 → 子] 委派预算审查：总额 272000 元，预算 268000 元。
[子 → 父] 已通过校验的结果：{"gap_yuan":4000,"reason":"..."}
[父 Agent] 收到工具结果，继续生成汇总。
[父 Agent 汇总] ...
```

子 Agent 失败时不会打印成功返回；父级请求预算不足时可能已经收到子结果，却无法再
请求模型汇总。离线测试的第二个场景会显示这种边界。

子 Agent 通过 `deps=ctx.deps` 获得可信业务事实；没有传父级 `message_history`，因此
父级完整对话不会自动进入子 Agent。最终子结果作为工具返回值进入父级消息。
这与 Deep Agents 的任务委派概念相近，但 API 与状态传播规则不同。

关键参数是 `usage=ctx.usage` 和 `usage_limits=ctx.usage_limits`。两级 Agent 共用
用量对象与上限，子任务不会凭空得到独立无限预算。离线测试规定父级请求工具、子级返回
结构化结果、父级汇总，合计 3 次模型请求；把上限改为 2 时必须失败。

本例是同一进程内的异步委派，没有后台任务、远程 Agent Server 或并行主管。
同一个模型客户端可以供两级 Agent 复用；Agent 的角色来自各自 instructions 与输出类型。

下一步：[08 · 人工审批](../08_human_approval/README.md)。

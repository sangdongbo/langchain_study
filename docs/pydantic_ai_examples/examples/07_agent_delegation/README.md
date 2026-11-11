# 07 · Agent 委派与共享预算

## 为什么需要两个 Agent

父 Agent 负责沟通与汇总，预算专家负责返回 `BudgetReview`。父 Agent 把子 Agent 包装
成一个普通异步工具，模型调用这个工具时，Python 执行 `await child.run(...)`。

前面一个 Agent 同时面对用户并处理任务。这里把“算清预算缺口并校验”分成独立子任务，
让子 Agent 专注输出可检查的对象，父 Agent 根据这个对象组织给用户看的文字。
这用于演示委派机制；实际业务若只是做一次减法，普通 Python 工具已经够用。

两个 Agent 不要求使用两个不同的大模型。本例共用一个模型客户端，角色区别来自指令、
工具和输出类型。多写一个 Agent 也不自动带来并发执行或独立后台进程。

## 先分清四种对象

| 对象 | 谁提供 | 做什么 |
| --- | --- | --- |
| `ReviewFacts` | 调用方 | 保存总额 `272000` 和预算 `268000`，供父子共同读取 |
| 父 Agent | 本课 `build_agents()` | 把任务委派出去，最终输出 `str` |
| 子 Agent | 本课 `build_agents()` | 返回 `BudgetReview`，并校验缺口是否等于真实差额 |
| `BudgetReview` | 子模型提出字段，程序校验 | 包含非负的 `gap_yuan` 和说明 `reason` |

`delegate_budget_review` 是父 Agent 的工具，函数体里才真正调用子 Agent。模型提出
这个工具调用后，Python 等待子 Agent 完成；子结果作为工具返回值交给父模型。

## 对照 run.py 看执行过程

1. 父模型收到用户任务，提出 `delegate_budget_review` 工具调用。
2. 工具使用 `deps=ctx.deps` 把可信金额传给子 Agent，同时传入共享用量和上限。
3. 子模型生成 `BudgetReview`，字段校验和 `validate_gap()` 确认缺口为 `4000`。
4. 工具返回这个对象，父模型读取工具结果后生成中文汇总。

这里等待的是子任务的最终结果；父级没有在等待过程中并行处理另一个业务任务。

## 怎样运行

```powershell
uv run python examples/07_agent_delegation/test.py
uv run python examples/07_agent_delegation/run.py
```

## 调用关系和输出怎么看

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

## 为什么要共享 usage

本课的“共享预算”指模型请求的用量限制，与 `ReviewFacts.budget_yuan` 中的采购预算
不同。`RunUsage` 记录已经消耗的用量，`UsageLimits` 定义允许消耗多少；仅传同一个
上限数值，不能替代共享已经累积的计数。

关键参数是 `usage=ctx.usage` 和 `usage_limits=ctx.usage_limits`。两级 Agent 共用
用量对象与上限，子任务不会凭空得到独立无限预算。离线测试规定父级请求工具、子级返回
结构化结果、父级汇总，合计 3 次模型请求；把上限改为 2 时必须失败。

本例是同一进程内的异步委派，没有后台任务、远程 Agent Server 或并行主管。
同一个模型客户端可以供两级 Agent 复用；Agent 的角色来自各自 instructions 与输出类型。

离线成功路径的请求计数可以这样核对：

| 次序 | 模型请求 | 累计请求数 |
| --- | --- | --- |
| 1 | 父模型提出委派工具调用 | 1 |
| 2 | 子模型提交结构化评审结果 | 2 |
| 3 | 父模型根据工具结果汇总 | 3 |

Python 执行工具本身不是一次模型请求，但工具内部调用子模型会增加请求计数。
真实模型若触发重试或额外工具调用，请求数可能增加，本例不承诺固定三次。

`test.py` 除了验证成功汇总，还把请求上限设为 2，确认第三次请求被
`UsageLimitExceeded` 阻止，最后打印 `07 PASS`。这时子结果可以已经产生，父级文字
汇总仍然失败；不能把“已收到子结果”和“整个任务完成”混为一谈。

上一课：[06 · 流式输出](../06_streaming/README.md)。
下一步：[08 · 人工审批](../08_human_approval/README.md)。

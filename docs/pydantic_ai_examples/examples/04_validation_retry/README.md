# 04 · 校验与重试

## 字段合法，为什么还会答错

第 02 课校验字段形状，这一课校验业务事实：总额超过预算时必须拒绝。
`approve` 字符串类型正确，却可能是业务错误，因此还需要 `output_validator`。

本课用两层校验解决不同问题：

| 校验层 | 负责检查 | 一个会被拒绝的例子 |
| --- | --- | --- |
| Pydantic 字段校验 | 是否满足 `Recommendation` 的类型与约束 | `verdict="maybe"` 不在允许值中 |
| Agent 业务校验 | 已合法的字段是否符合当前采购事实 | 总额超预算，仍给出 `verdict="approve"` |

`Recommendation` 是输出数据类，`ReviewFacts` 是程序提供的可信事实容器。
`Literal["approve", "reject"]` 表示只接受这两个结论词值；它不包含“什么时候应当批准”
这条规则。这里“预算”指采购预算，后面 `UsageLimits` 的请求预算是另一个概念。

## output_validator 和 ModelRetry 分别做什么

`@agent.output_validator` 把函数登记为最终输出的业务检查步骤。它在字段校验成功后
执行，读取 `ctx.deps` 和模型提交的对象。满足规则就返回对象，让运行继续完成；不满足
就抛出 `ModelRetry`，把“应当怎样修正”的信息反馈给模型。

`ModelRetry` 是控制框架修正流程的异常，不是自己用 `while` 循环再次运行整段脚本。
框架保留本次消息和用量，让模型基于错误提示重新尝试；能否继续还取决于剩余上限。

## 对照 run.py 看执行过程

1. `main()` 创建事实：采购总额 `272000` 元、预算 `268000` 元。
2. `@agent.instructions` 注册的 `policy()` 根据本次 `deps` 生成指令，让模型看到事实。
   这是运行时生成指令，区别于第一课直接传固定字符串。
3. 模型提交包含 `verdict` 和 `reason` 的 `Recommendation`。
4. Pydantic 检查字段，`validate_decision()` 再计算本次应有的结论并对照。
5. 正确就返回结果，错误就发出修正提示；重试耗尽或用量超限则报错停止。

## 怎样运行

```powershell
uv run python examples/04_validation_retry/test.py
uv run python examples/04_validation_retry/run.py
```

## 如何观察一次修正

真实模型可能第一次就答对，因此不保证演示中一定发生重试。
离线测试刻意先返回 `approve` 再返回 `reject`，确定性验证真实的两次请求和重试消息。

终端直接展示实际校验过程。例如运行 `test.py` 的第一个场景：

```text
[校验] 模型结论=approve，预算规则要求=reject
[需修正] 结论冲突，提交 ModelRetry；是否重试由剩余上限决定。
[校验] 模型结论=reject，预算规则要求=reject
[通过] 结论与预算事实一致，接受本次输出。
```

这些信息来自同一个业务 validator，真实演示也会显示。模型首次答对时只出现一次校验
与通过信息。测试还分场景展示边界通过、重试耗尽和请求预算阻止。
「需修正」表示校验失败，不保证会发出下一次请求；已耗尽重试或用量上限时直接失败。

重试不是无限循环。`retries=2` 限制输出修正，耗尽会抛出
`UnexpectedModelBehavior`；`UsageLimits(request_limit=1)` 可更早阻止第二次请求，
抛出 `UsageLimitExceeded`。测试覆盖这两条失败路径，以及总额等于预算时允许的边界。

只有模型能修正的错误适合 `ModelRetry`。权限不足、服务宕机或网络错误需要调用方处理，
不要把所有异常都改成重试提示。这个校验只检查 verdict，不证明 reason 中的每句话真实。

## 怎样判断运行成功

成功结果的 `verdict` 应为 `reject`，并显示合法的 `reason` 和用量。离线检查会故意制造
重试耗尽、请求上限不足的场景，捕获对应异常并打印 `[已阻止]`，最终出现 `04 PASS`。
这些异常是测试要验证的行为；如果自己的真实脚本抛出未处理异常，则这次运行没有成功。

`retries=2` 表示本课允许最多两次输出修正，首次生成也会消耗模型请求。
`UsageLimits(request_limit=1)` 限制整个运行只能请求一次，因此即使修正次数尚有剩余，
也不能发出第二次请求。两种限制要分别理解。

上一课：[03 · 工具与依赖](../03_tools_and_deps/README.md)。
下一步：[05 · 多轮对话](../05_message_history/README.md)。

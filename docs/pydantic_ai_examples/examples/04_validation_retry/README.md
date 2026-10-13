# 04 · 校验与重试

第 02 课校验字段形状，这一课校验业务事实：总额超过预算时必须拒绝。
`approve` 字符串类型正确，却可能是业务错误，因此还需要 `output_validator`。

```powershell
uv run python examples/04_validation_retry/test.py
uv run python examples/04_validation_retry/run.py
```

`ReviewFacts` 由调用方提供，不由模型填写。动态 `@agent.instructions` 把本次评审事实
告诉模型；`@agent.output_validator` 在接受最终输出前再次读取相同事实。
模型结论不匹配时抛出 `ModelRetry`，框架把修正提示发送给模型。

本例流程为：模型提交 Recommendation → Pydantic 字段校验 → 业务结论校验 →
接受，或带错误再次请求模型。真实模型可能第一次就答对，因此不保证演示中一定发生重试。
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

下一步：[05 · 多轮对话](../05_message_history/README.md)。

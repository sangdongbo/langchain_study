# 03 · 工具与依赖注入

采购总额由 Python 工具计算，预算来自内存字典。模型负责选择并调用工具，不能用自己
编造的预算代替工具结果。这个业务与 Deep Agents 采购示例一致，方便对照框架 API。

```powershell
uv run python examples/03_tools_and_deps/test.py
uv run python examples/03_tools_and_deps/run.py
```

`@agent.tool_plain` 注册不需要上下文的 `calculate_total`；`@agent.tool` 注册需要
`RunContext[PurchaseDeps]` 的 `check_budget`。框架从函数参数生成工具 schema，
正数约束也进入参数校验。`ctx` 不属于模型填写的工具参数。

调用方通过 `run_sync(..., deps=PurchaseDeps(...))` 传入租户和预算数据。工具只访问
`ctx.deps.tenant_id` 对应的数据，模型没有选择租户的参数。认证租户必须由可信服务端
确定；本例硬编码 `tenant-a`，用于演示边界，不能当作完整认证实现。

运行时会打印工具返回值：总额 `272000`、预算 `268000`、缺口 `4000`。
测试还以相同参数访问 `tenant-b`，验证返回其独立预算，并检查未知租户被拒绝、数量为零
时生成重试提示。字典模拟业务数据，全程不连接数据库。

`ModelRetry` 用于模型可修正的部门名称错误；权限错误直接终止运行。
模型调用工具的选择和次数可能变化，真实演示设置请求与工具次数上限。

下一步：[04 · 校验与重试](../04_validation_retry/README.md)。

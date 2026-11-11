# 03 · 工具与依赖注入

## 这一课比前面增加了什么

采购总额由 Python 工具计算，预算来自内存字典。模型负责选择并调用工具，不能用自己
编造的预算代替工具结果。这个业务与 Deep Agents 采购示例一致，方便对照框架 API。

第 02 课在模型输出后由 Python 计算；这里把函数注册为工具，模型可以在形成最终回答
之前提出计算和预算查询请求。instructions 要求先算再查，真实模型是否遵循仍需检查
工具记录；仅写“必须调用”不等于程序已经强制执行该步骤。

## 工具是什么，谁执行它

工具就是你允许 Agent 使用的 Python 函数。模型看到函数说明和参数结构，返回工具名
与参数；框架检查参数后执行函数，把返回值作为工具消息交给模型。模型不会直接读取
你的整个内存字典，也不会自动获得运行任意代码的权限。

代码中的 `@agent.tool_plain` 和 `@agent.tool` 是 **装饰器**：把紧随其后的函数登记为
这个 Agent 的工具。定义时进行登记；只有运行中实际提出调用时，函数体才会执行。

| 工具注册方式 | 函数能使用什么 | 本课函数 |
| --- | --- | --- |
| `@agent.tool_plain` | 模型提交的普通参数 | `calculate_total(quantity, unit_price_yuan)` |
| `@agent.tool` | 普通参数，加上框架提供的 `RunContext` | `check_budget(ctx, department, amount_yuan)` |

`Annotated[int, Field(gt=0)]` 的基础类型是整数，附加约束是“大于零”；这样工具参数
也可以被校验。工具函数的文档字符串用于描述它做什么，参数类型用于描述怎样调用。

## deps 是本次业务数据，不是需要安装的依赖包

这里的“依赖注入”表示：由调用方把本次任务需要的数据或服务传给 Agent，工具需要时
通过运行上下文取得。`PurchaseDeps` 保存当前租户 `tenant_id` 和预算字典 `budgets`。
它使用 Python 标准库的 `@dataclass` 简化数据容器定义，本身没有 Pydantic 那样的
运行时字段校验。

`deps_type=PurchaseDeps` 声明预期类型，`deps=PurchaseDeps("tenant-a", BUDGETS)`
才提供实际值；`ctx.deps` 读取这份对象。`RunContext` 还携带当前用量等运行信息，
本课先关注 `deps` 即可。

`ctx` 由框架注入，不由模型填写。依赖对象也不会自动整份变成模型提示；工具返回值和
动态指令中主动使用的内容仍可能进入模型请求，因此应按需要选择传回模型的业务信息。

## 对照 run.py 看执行过程

1. `main()` 选择可信租户 `tenant-a`，将它和预算字典放入 `PurchaseDeps`。
2. 模型提出计算工具请求，Python 计算 `4 × 68000 = 272000`。
3. 模型使用计算结果提出预算查询；框架提供 `ctx`，模型只填部门和金额。
4. `check_budget()` 先按 `ctx.deps.tenant_id` 限定数据范围，再读取部门预算。
5. 工具返回预算、金额、是否充足和缺口；模型据此汇总。程序另行打印实际工具返回片段。

## 怎样运行

```powershell
uv run python examples/03_tools_and_deps/test.py
uv run python examples/03_tools_and_deps/run.py
```

## 权限和可修正错误怎么处理

认证租户必须由可信服务端确定，不能交给模型填写。未知租户直接触发 `PermissionError`
终止运行；部门名称可能写错，则使用 `ModelRetry` 让模型核对参数后修正。
测试还检查数量为零时在工具执行前生成重试提示。模型调用工具的选择和次数可能变化，
真实演示设置请求与工具次数上限；字典模拟业务数据，全程不连接数据库。

## 运行结果怎么看

`calculate_total` 返回 `272000`；`check_budget` 返回的 `enough` 为 `False`，
`budget_yuan` 为 `268000`，`gap_yuan` 为 `4000`。`tool: ... => ...` 是实际执行函数
得到的内容，用它核对金额，不能只看模型最终回答里的“我已经查过”。

`test.py` 用本地 `FunctionModel` 指定工具调用顺序，但执行的仍是 `run.py` 的工具。
它同时检查两个租户、非法数量和未知租户，成功后显示 `03 PASS`。真实服务中的租户
身份还需要经过认证；本课的固定身份只展示如何把这个边界传给工具。

上一课：[02 · 结构化输出](../02_structured_output/README.md)。
下一步：[04 · 校验与重试](../04_validation_retry/README.md)。

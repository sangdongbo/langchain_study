# 02 · 结构化输出

模型抽取部门、物品、数量、单价、供应商；Python 取得 `Purchase` 对象后计算总额。
这样程序可以读取 `result.output.quantity`，无需从自然语言中再次解析数字。

```powershell
uv run python examples/02_structured_output/test.py
uv run python examples/02_structured_output/run.py
```

关键代码是 `Agent(..., output_type=Purchase)`。默认工具输出模式会让模型通过输出工具
提交符合 schema 的参数；供应商需要支持 tool calling。这里没有使用供应商可能不支持
的原生 JSON Schema 输出模式。

`Field(gt=0)` 拒绝零或负数，`min_length=1` 拒绝空名称。类型/schema 校验失败时，
框架可以把错误交给模型重新生成；`retries=2` 限制这种修正次数。
类型正确不等于内容真实：框架无法自动证明供应商名称来自输入，业务事实校验见第 04 课。

预期输出包含 `quantity: 4` 和 `unit_price_yuan: 68000`，程序计算结果为 `272000 元`。
本例的金额单位固定为整数元；需要小数金额时先改为整数分或明确的 Decimal 方案，
再调整 schema 与计算，避免浮点金额运算。

输入样例给出了全部字段。本课不实现缺字段追问或真实采购提交。

下一步：[03 · 工具与依赖](../03_tools_and_deps/README.md)。

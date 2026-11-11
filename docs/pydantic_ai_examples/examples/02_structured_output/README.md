# 02 · 结构化输出

## 为什么不能只让模型“回答一段 JSON”

模型抽取部门、物品、数量、单价、供应商；Python 取得 `Purchase` 对象后计算总额。
这样程序可以读取 `result.output.quantity`，无需从自然语言中再次解析数字。

上一课的结果是文字，适合给人看。这一课要让程序继续计算，需要明确的字段和类型。
仅在提示词中要求“返回 JSON”不能保证数量合法、字段齐全，也不会自动创建 Python 对象。

## 先理解 BaseModel、Field 和 schema

`Purchase` 继承 Pydantic 的 `BaseModel`，表示“采购数据应具有以下结构”。它不是一个
大语言模型，也不会发出网络请求。`Field` 把字段说明和具体约束写在结构定义里：

| 字段 | 类型与约束 | 校验的内容 |
| --- | --- | --- |
| `department`、`item`、`supplier` | `str`，`min_length=1` | 必须提供，且至少有一个字符 |
| `quantity` | `int`，`gt=0` | 必须是校验后的正整数 |
| `unit_price_yuan` | `int`，`gt=0` | 必须是校验后的正整数元金额 |

没有默认值的字段在这里都是必填项。`gt` 是 greater than（大于），`min_length` 是
最小长度；`description` 描述字段含义，帮助模型填写，不代替数值或长度约束。
`min_length=1` 仍允许全空格字符串，不能直接当作完整的名称有效性校验。

框架把字段和约束转换成模型能理解的 **schema（结构说明）**。`output_type=Purchase`
把这份结构设为 Agent 的最终输出要求；只有校验成功，程序才取得 `Purchase` 对象。
Pydantic 默认允许部分类型转换，例如把 `"4"` 转为整数 `4`，这里没有开启严格模式。

## 对照 run.py 看执行过程

1. `PROMPT` 提供一段完整采购需求，`Purchase` 定义要抽取的字段。
2. `build_agent()` 设置 `output_type=Purchase`，向模型说明最终输出结构。
3. 模型提交字段，PydanticAI 借助 Pydantic 检查类型、必填项和约束。
4. 合法时得到 `result.output`；不合法时可以在剩余重试次数内要求模型修正。
5. Python 读取数量和单价相乘，得到 `272000` 元；这个乘法由程序执行。

## 怎样运行

```powershell
uv run python examples/02_structured_output/test.py
uv run python examples/02_structured_output/run.py
```

## 框架具体怎样取得对象

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

## 运行结果怎么看

真实演示先用 `result.output.model_dump_json(indent=2)` 把已经得到的对象转成缩进的
JSON 字符串，方便展示；调用它不表示“再请模型生成一次 JSON”。结果应类似：

```json
{
  "department": "研发平台部",
  "item": "AI 推理服务器",
  "quantity": 4,
  "unit_price_yuan": 68000,
  "supplier": "北辰智能硬件"
}
```

随后显示 `程序计算总额：272000 元`。离线 `test.py` 还会尝试数量为 0、单价为负数、
供应商为空字符串，确认 Pydantic 抛出 `ValidationError`，最后打印 `02 PASS`。

字段校验能保证对象满足声明的结构，不能保证模型没有编造一个合法但错误的名称。
需要把结论与可信业务事实对照时，继续学第 04 课。

上一课：[01 · 基础 Agent](../01_basic_agent/README.md)。
下一步：[03 · 工具与依赖](../03_tools_and_deps/README.md)。

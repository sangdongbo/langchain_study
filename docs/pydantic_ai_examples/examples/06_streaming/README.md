# 06 · 流式输出

## 这一课解决什么问题

前面的 `run_sync()` 等待完整答案，这一课把文字增量立即打印到终端。
核心写法是 `async with agent.run_stream(...) as result`，在上下文内消费异步流。

流式输出改变的是“怎样接收和展示答案”：模型服务不断交付文本片段，程序收到一段就
显示一段。它不会让尚未完成的回答提前变成最终结果，也不保证减少整次任务的总耗时。
输出类型仍是 `str`，没有因此换成另一个 Agent。

## 看懂异步写法

| 语法 | 在本课中的意思 |
| --- | --- |
| `async def main()` | 定义可以等待异步操作的入口；调用它得到协程，需要进一步运行 |
| `async with agent.run_stream(...)` | 打开本次流式运行，并在退出时管理流资源 |
| `async for delta in ...` | 等待下一段文本，收到后执行循环体，直到流结束 |
| `await result.get_output()` | 等待并取得完整结果；不要忘记 `await` |
| `asyncio.run(main())` | 在普通脚本中启动事件循环来执行协程 |

`async` 不表示代码会自动并行。本课只有一个流，目标是边等待边展示。Notebook 已有
事件循环时直接 `await main()`，不再套 `asyncio.run()`。

## 增量文字与累计文字有什么区别

假设完整回答是“检查预算”：

| 模式 | 第一次收到 | 第二次收到 | 显示方式 |
| --- | --- | --- | --- |
| `delta=True`，增量 | `检查` | `预算` | 每次追加，得到“检查预算” |
| `delta=False`，累计 | `检查` | `检查预算` | 每次替换已有内容 |

如果把累计模式也直接追加，就会显示成“检查检查预算”。本课在终端追加输出，所以
明确选择 `delta=True`。这些片段只用于解释，真实服务的分块不保证按词、汉字或 token 对齐。
`debounce_by=None` 关闭输出合并间隔，方便教学观察，不决定模型服务怎样分块。

## 对照 run.py 看执行过程

1. 创建 Agent，使用 `run_stream()` 开始一次流式运行。
2. 在 `async with` 内用 `stream_text(delta=True, debounce_by=None)` 读取增量。
3. `print(delta, end="", flush=True)` 不换行并立即刷新，显示已经收到的文字。
4. 流消费结束后取得完整结果，再打印字符数和最终用量。

`len(output)` 是 Python 字符串长度，不是 token 数量，也不能直接换算 API 费用。

## 怎样运行

```powershell
uv run python examples/06_streaming/test.py
uv run python examples/06_streaming/run.py
```

## 运行结果怎么看

消费完成后，`await result.get_output()` 取得完整答案，`result.usage` 才有完整用量。
离线测试用 `FunctionModel(stream_function=...)` 提供固定分块，检查拼接结果与最终
输出一致，并确认流已经完成；不依赖网络速度或模型分块方式。

本例没有工具调用，只展示最终文字流。如果需要逐个观察模型请求、工具开始/结束或
Agent 节点，应使用框架事件流/迭代接口，不能把 `stream_text()` 当成所有执行事件。
本课也没有把未完成的流式文字用于业务提交。

离线运行没有网络等待，文字可能瞬间全部显示；`test.py` 检查的是确实收到多个片段、
拼接内容与完整答案一致、运行已经完成，成功后显示 `06 PASS`。真实模型通常能观察到
逐步输出，但显示节奏受模型服务、网络和终端缓冲影响。

上一课：[05 · 多轮对话](../05_message_history/README.md)。
下一步：[07 · Agent 委派](../07_agent_delegation/README.md)。

# 01 · 基础 Agent

这一课只做一件事：给模型一条 instructions 和一个用户问题，取得文字结果。
`build_agent()` 定义行为，`run_sync()` 或 `await agent.run()` 执行一次运行，
`result.output` 是最终回答，`result.usage` 是框架累计的请求和 token 用量。

从示例项目根目录运行：

```powershell
uv run python examples/01_basic_agent/test.py
uv run python examples/01_basic_agent/run.py
uv run python examples/01_basic_agent/run.py --async
uv run python examples/01_basic_agent/run.py --prompt "什么场景适合使用工具调用？"
```

先观察同步、异步两种写法的结果结构，再看 usage 中的 `requests`。一个 run 可以包含
多次模型请求；这里设置 `request_limit=3`，后面加入工具后会看到请求次数增加。
这个参数限制请求数量，不代表费用或 token 的精确上限。

在 Notebook 的已有事件循环中使用 `await agent.run(...)`，不要调用 `run_sync()`
或 `asyncio.run()`。当前 Python 文件中的 `asyncio.run()` 是终端入口的写法。

离线测试使用官方 `TestModel` 指定一条回答，同时验证同步与异步入口。它不证明真实
模型一定按 instructions 回答；下一课会让输出由 Pydantic 校验。

下一步：[02 · 结构化输出](../02_structured_output/README.md)。

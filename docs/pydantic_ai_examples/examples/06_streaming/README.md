# 06 · 流式输出

前面的 `run_sync()` 等待完整答案，这一课把文字增量立即打印到终端。
核心写法是 `async with agent.run_stream(...) as result`，在上下文内消费异步流。

```powershell
uv run python examples/06_streaming/test.py
uv run python examples/06_streaming/run.py
```

`stream_text(delta=True)` 每次返回新增文字，可以直接追加；默认 `delta=False` 返回
截至当时的累计文字，直接追加会产生重复内容。`debounce_by=None` 关闭输出合并间隔，
方便教学观察，不代表网络一定按固定字数或 token 数量分块。

消费完成后，`await result.get_output()` 取得完整答案，`result.usage` 才有完整用量。
离线测试用 `FunctionModel(stream_function=...)` 提供固定分块，检查拼接结果与最终
输出一致，并确认流已经完成；不依赖网络速度或模型分块方式。

本例没有工具调用，只展示最终文字流。如果需要逐个观察模型请求、工具开始/结束或
Agent 节点，应使用框架事件流/迭代接口，不能把 `stream_text()` 当成所有执行事件。
本课也没有把未完成的流式文字用于业务提交。

下一步：[07 · Agent 委派](../07_agent_delegation/README.md)。

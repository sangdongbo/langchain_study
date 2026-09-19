# 并行采购审查

本例把财务、库存和供应商风险拆成三个子 Agent。父模型必须在同一轮响应中生成
三个 `task` 工具调用，LangGraph 的工具节点才能并发执行它们。

## 执行流程

```text
                         -> finance-reviewer   -┐
用户请求 -> parent model -> inventory-reviewer -+-> parent model -> 汇总结论
                         -> supplier-reviewer  -┘
```

“配置了三个子 Agent”不等于自动并行。如果父模型分三轮分别调用 `task`，执行仍然
是串行的；只有一条 `AIMessage` 同时包含三个工具调用时，工具节点才会并发调度。

## 离线测试如何证明并行

测试中的三个编译式子 Agent 共用 `threading.Barrier(3)`。每个任务进入后必须等待
另外两个任务：

- 并行执行时，三个任务都到达屏障并继续运行。
- 串行执行时，第一个任务等不到另外两个，会在超时后直接失败。

这比只比较日志时间或依赖很小的耗时阈值更稳定。

## 运行

```powershell
# 需要模型 Key，可在 LangSmith 中观察三条并行 task 轨迹
uv run python examples/parallel_review/run.py

# Fake Model + Barrier，不需要 Key，不访问网络
uv run python examples/parallel_review/test.py
```

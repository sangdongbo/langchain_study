# 工具失败恢复

本例使用 LangChain 原生 `ToolRetryMiddleware`，把短暂故障的重试放在一次工具
调用内部完成。模型只生成一次工具调用，不需要自己猜测应该重试多少次。

## 两种结果

```text
工具第一次执行
  -> TimeoutError
  -> 按退避策略重试
  -> 成功：正常 ToolMessage 返回模型

工具第一次执行
  -> ConnectionError
  -> 重试仍失败
  -> on_failure 生成 status=error 的 ToolMessage
  -> 模型根据降级信息继续回答
```

`max_retries=2` 表示“初次调用失败后最多再试两次”，因此总尝试次数最多为 3。
`retry_on` 应只包含明确可恢复的异常；参数错误、权限错误等永久故障应立即抛出。

## 副作用工具注意事项

本例重试的是只读查询。支付、发布、创建订单等工具如果没有幂等键，超时可能表示
“服务端已经成功，但客户端没有收到响应”，直接重试会造成重复写入。此类工具必须
先设计幂等协议，再启用自动重试。

## 运行

```powershell
# 前两次失败，第三次成功
uv run python examples/tool_failure_recovery/run.py --failures 2

# 超过重试次数，模型收到降级错误
uv run python examples/tool_failure_recovery/run.py --failures 4

# Fake Model，不需要 Key，不访问网络，也不实际等待退避时间
uv run python examples/tool_failure_recovery/test.py
```

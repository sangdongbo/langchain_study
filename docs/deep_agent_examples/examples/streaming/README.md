# Streaming 与子 Agent 事件

本例演示如何使用 LangGraph 的 `stream()` 观察 Agent 的增量执行过程，而不是只
等待 `invoke()` 返回最终 State。

## 事件类型

```text
updates  -> 节点完成后的 State 增量，例如 model、tools
messages -> 模型 token 和调用元数据
tasks    -> 节点/任务开始和结束（可按需加入）
```

本例使用 `version="v2"`，每个事件都有统一结构：

```python
{
    "type": "updates" | "messages",
    "ns": ("子图命名空间", ...),
    "data": ...,
}
```

`subgraphs=True` 后，子 Agent 的事件也会流出来。`ns` 为空通常表示父 Graph；
非空表示嵌套 Graph。不要用日志文字猜测父子关系，应使用这个命名空间。

## 运行

```powershell
# 需要模型 Key；会打印模型/工具事件和子图命名空间
uv run python examples/streaming/run.py

# Fake Model，不需要 Key、不访问网络
uv run python examples/streaming/test.py
```

生产 Web API 通常把这些事件转成 SSE/WebSocket；终端示例只做文本打印，不代表
必须使用某一种传输协议。


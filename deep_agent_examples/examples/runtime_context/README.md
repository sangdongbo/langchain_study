# Runtime Context 与租户边界

本例演示 `context_schema` 和 `ToolRuntime.context`。Runtime Context 是一次调用
携带的只读上下文，适合用户 ID、租户 ID、角色、功能开关等请求级信息。

## 它和 State 的区别

```text
State          -> 对话/Graph 状态，可进入 checkpoint，适合 messages、todos、files
Runtime Context -> 本次调用上下文，工具通过 ToolRuntime.context 读取，不是用户消息
```

不要把租户或角色直接放在用户文本里让模型“自证”。生产环境应由认证层构造
`context`，工具或 Middleware 再据此做授权和数据隔离。

## 执行流程

```text
服务端认证
  -> context={tenant_id, role, feature_flags}
  -> create_deep_agent(context_schema=...)
  -> 工具通过 ToolRuntime.context 读取
  -> 工具按租户和角色返回允许的结果
```

## 运行

```powershell
# 需要模型 Key
uv run python examples/runtime_context/run.py

# Fake Model，不需要 Key、不访问网络
uv run python examples/runtime_context/test.py
```

## 观察重点

Runtime Context 不会自动出现在用户消息中。模型只有在调用工具后，才能看到工具
根据上下文返回的结果；这比把内部租户信息拼进 prompt 更容易集中控制。


# Checkpoint 中断与恢复

本例演示 Agent 在执行副作用工具前中断，把现场保存到 Checkpointer，然后使用
同一个 `thread_id` 恢复。恢复时可以重新创建 Graph 对象，不要求保留原对象。

## 执行流程

```text
用户请求
  -> model 生成 reserve_budget 工具调用
  -> HITL Middleware 触发 interrupt
  -> Checkpointer 保存消息、待执行节点和中断信息
  -> 人工 approve/reject
  -> Command(resume=...) 使用同一 thread_id 恢复
  -> approve 才真正执行 reserve_budget
  -> model 输出最终结论
```

`thread_id` 是 Checkpoint 的会话主键。换一个 `thread_id` 就是另一条执行历史，
不能恢复当前中断。

## 为什么示例使用 InMemorySaver

`InMemorySaver` 不增加依赖，适合验证协议和编写离线测试。它只保证当前 Python
进程内的恢复，进程退出后记录消失。生产系统需要换成数据库支持的 Checkpointer，
并保证 API 恢复请求继续使用原 `thread_id`。

## 运行

```powershell
# 需要模型 Key
uv run python examples/durable_resume/run.py --decision approve
uv run python examples/durable_resume/run.py --decision reject

# Fake Model，不需要 Key，不访问网络
uv run python examples/durable_resume/test.py
```

离线测试还会验证：批准前工具没有执行、Graph 重建后可以恢复，以及不同 thread
之间的 Checkpoint 完全隔离。

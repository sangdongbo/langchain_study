# Memory 与 AGENTS.md

本例演示 Deep Agents 的 Memory 和 Skill 的区别，以及如何使用
`StoreBackend` 让 `AGENTS.md` 在不同 thread 之间持续存在。

## 和 Skill 的区别

```text
Memory（AGENTS.md） -> 每次 Agent 启动时自动加载，提供长期规则和偏好
Skill（SKILL.md）   -> 先展示目录索引，模型判断需要时再读取完整流程
```

Memory 不是用户消息，也不是隐藏的权限配置。它只是上下文参考；真正的权限仍然
由工具、Middleware、HITL 和沙箱控制。

## 执行流程

```text
StoreBackend(namespace=tenant-a)
  -> 保存 /AGENTS.md
  -> MemoryMiddleware.before_agent 读取文件
  -> <agent_memory> 注入模型 system prompt
  -> 不同 thread 使用同一份租户记忆
```

`StateBackend` 只能在同一个 checkpointed thread 中保存文件；本例换成
`StoreBackend` 后，`memory-a` 和 `memory-b` 两个 thread 仍能读取同一份记忆。
生产环境应使用真正持久化的 Store，并让 namespace 来自服务端认证身份。

## 运行

```powershell
# 需要模型 Key
uv run python examples/memory/run.py

# Fake Model，不需要 Key、不访问网络
uv run python examples/memory/test.py
```

真实运行会打印租户、两个 thread 和 Memory 文件路径。启用 LangSmith 后，可以
在模型 span 的 system message 中查看 `<agent_memory>` 内容。


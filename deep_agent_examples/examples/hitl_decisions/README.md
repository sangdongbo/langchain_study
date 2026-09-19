# HITL 多种审核决策

本例为有副作用的 `publish_decision` 工具启用三种人工决策：

| 决策 | 工具是否执行 | 使用的参数 |
| --- | --- | --- |
| `approve` | 是 | 模型原始参数 |
| `edit` | 是 | 人工提供的 `edited_action.args` |
| `reject` | 否 | 不适用，模型收到错误 ToolMessage |

## 执行流程

```text
model 生成 publish_decision
  -> HumanInTheLoopMiddleware.after_model
  -> interrupt(action_requests + review_configs)
  -> Command(resume={decisions: [...]})
  -> approve/edit: 执行工具
  -> reject: 合成 status=error 的 ToolMessage，不执行工具
  -> model 根据审核结果继续回答
```

一次中断可能包含多个待审核动作，因此 `decisions` 的数量和顺序必须与
`action_requests` 一致。本例只有一个发布动作，所以恢复时只传一个 decision。

`respond` 是框架支持的第四种决定，可以由人工直接提供 ToolMessage 内容并跳过工具；
本例没有启用它，以便集中展示发布场景最常见的批准、修改和拒绝。

## 运行

```powershell
# 需要模型 Key
uv run python examples/hitl_decisions/run.py --decision approve
uv run python examples/hitl_decisions/run.py --decision edit
uv run python examples/hitl_decisions/run.py --decision reject

# Fake Model，不需要 Key，不访问网络
uv run python examples/hitl_decisions/test.py
```

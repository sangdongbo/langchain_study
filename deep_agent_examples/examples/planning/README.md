# Todo 任务规划

本例演示官方文档中的 `TodoListMiddleware` 和 `write_todos`。它适合复杂、多步骤
任务，不是所有请求都应该使用的普通清单工具。

## 执行流程

```text
用户提出复杂任务
  -> model 调用 write_todos
  -> Middleware 把完整任务清单写入 State.todos
  -> model 继续执行任务
  -> 后续 write_todos 把项目标记为 completed
  -> 最终回答在最后一次 write_todos 之后生成
```

`write_todos` 每次会替换整个清单，所以同一轮不能并行调用。它的状态会跟随
checkpoint 保存；如果要恢复中断任务，必须继续使用同一个 `thread_id`。

## 运行

```powershell
# 需要模型 Key
uv run python examples/planning/run.py

# Fake Model，不需要 Key、不访问网络
uv run python examples/planning/test.py
```

真实运行时可以在 LangSmith 的 model/tool 时间线中看到 `write_todos` 调用，
并在 Graph State 中查看 `todos` 的状态变化。


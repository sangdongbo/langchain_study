# 按顺序学习

每个目录包含 `README.md`、真实模型演示 `run.py` 和离线检查 `test.py`。
所有命令从 `docs/pydantic_ai_examples/` 执行，安装步骤见[总览](../README.md)。

| 顺序 | 专题 | 新增知识 | 演示命令 |
| --- | --- | --- | --- |
| 1 | [基础对话](01_basic_agent/README.md) | `Agent`、instructions、同步与异步运行 | `uv run python examples/01_basic_agent/run.py` |
| 2 | [结构化输出](02_structured_output/README.md) | `output_type`、Pydantic 字段校验 | `uv run python examples/02_structured_output/run.py` |
| 3 | [工具与依赖](03_tools_and_deps/README.md) | `tool`、`tool_plain`、`RunContext` | `uv run python examples/03_tools_and_deps/run.py` |
| 4 | [校验与重试](04_validation_retry/README.md) | `output_validator`、`ModelRetry`、预算限制 | `uv run python examples/04_validation_retry/run.py` |
| 5 | [多轮对话](05_message_history/README.md) | 消息历史传递、JSON 序列化 | `uv run python examples/05_message_history/run.py` |
| 6 | [流式输出](06_streaming/README.md) | `run_stream`、文本增量、usage | `uv run python examples/06_streaming/run.py` |
| 7 | [Agent 委派](07_agent_delegation/README.md) | 类型化子任务、父子 Agent 共用预算 | `uv run python examples/07_agent_delegation/run.py` |
| 8 | [人工审批](08_human_approval/README.md) | 延迟工具调用、批准、拒绝、恢复 | `uv run python examples/08_human_approval/run.py` |

对应检查命令把 `run.py` 换成 `test.py`。一次检查全部专题：

```powershell
uv run python scripts_smoke.py
```

建议先读代码中的 `build_agent()`，再运行 `test.py` 看确定性结果，最后配置 Key 运行
`run.py` 观察真实模型的选择。离线模型负责指定回答或工具调用，Agent 框架仍然真实执行。

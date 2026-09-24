# 专题示例

这个目录按功能保存可独立学习的 Deep Agents 示例。每个功能目录都有：

- `README.md`：原理、使用场景和详细说明。
- `run.py`：连接真实模型的演示入口。
- `test.py`：不需要 API Key 的离线测试。

| 目录 | 示例内容 | 真实演示命令 | 离线测试命令 |
| --- | --- | --- | --- |
| [async_subagent](async_subagent/README.md) | 通过 Agent Protocol 运行后台子 Agent | `uv run python examples/async_subagent/run.py` | `uv run python examples/async_subagent/test.py` |
| [compiled_subagent](compiled_subagent/README.md) | 把预编译 Graph 作为子 Agent | `uv run python examples/compiled_subagent/run.py` | `uv run python examples/compiled_subagent/test.py` |
| [declarative_subagent](declarative_subagent/README.md) | 声明式子 Agent 的 isolated/fork 模式 | `uv run python examples/declarative_subagent/run.py --mode isolated` | `uv run python examples/declarative_subagent/test.py` |
| [durable_resume](durable_resume/README.md) | 使用 Checkpoint 中断并恢复 Agent | `uv run python examples/durable_resume/run.py --decision approve` | `uv run python examples/durable_resume/test.py` |
| [dynamic_skills](dynamic_skills/README.md) | 根据身份和任务动态注入 Skill | `uv run python examples/dynamic_skills/run.py` | `uv run python examples/dynamic_skills/test.py` |
| [hitl_decisions](hitl_decisions/README.md) | 演示人工审核的 approve、edit、reject | `uv run python examples/hitl_decisions/run.py --decision edit` | `uv run python examples/hitl_decisions/test.py` |
| [lifecycle](lifecycle/README.md) | 观察普通 Agent 和子 Agent 生命周期 | `uv run python examples/lifecycle/run.py --kind agent` | `uv run python examples/lifecycle/test.py` |
| [parallel_review](parallel_review/README.md) | 并行委派三个独立采购审查任务 | `uv run python examples/parallel_review/run.py` | `uv run python examples/parallel_review/test.py` |
| [skill_versioning](skill_versioning/README.md) | 按 thread 隔离和切换 Skill 版本 | `uv run python examples/skill_versioning/run.py --version v2` | `uv run python examples/skill_versioning/test.py` |
| [tool_failure_recovery](tool_failure_recovery/README.md) | 工具失败后的自动重试和降级 | `uv run python examples/tool_failure_recovery/run.py --failures 2` | `uv run python examples/tool_failure_recovery/test.py` |
| [memory](memory/README.md) | AGENTS.md Memory、StoreBackend 与跨 thread 记忆 | `uv run python examples/memory/run.py` | `uv run python examples/memory/test.py` |
| [planning](planning/README.md) | TodoListMiddleware 与复杂任务规划 | `uv run python examples/planning/run.py` | `uv run python examples/planning/test.py` |
| [runtime_context](runtime_context/README.md) | context_schema、租户与角色运行时上下文 | `uv run python examples/runtime_context/run.py` | `uv run python examples/runtime_context/test.py` |
| [streaming](streaming/README.md) | v2 事件流、updates/messages 与子图 namespace | `uv run python examples/streaming/run.py` | `uv run python examples/streaming/test.py` |
| [composite_backend](composite_backend/README.md) | StateBackend 与 StoreBackend 按路径路由 | `uv run python examples/composite_backend/run.py` | `uv run python examples/composite_backend/test.py` |
| [feishu_mcp](feishu_mcp/README.md) | 外部飞书 MCP 工具发现、只读白名单与 Agent 总结 | `uv run python examples/feishu_mcp/run.py` | `uv run python examples/feishu_mcp/test.py` |

## 怎么启动

所有命令都从项目根目录执行：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }
uv sync
.\.venv\Scripts\Activate.ps1
```

如果终端提示符仍是其他项目名，说明激活了错误的虚拟环境；执行上面的
`deactivate` 和 `Activate.ps1` 后，提示符应显示 `(deep-agent-examples)`。

真实演示需要先在 `.env` 中配置模型 API Key。只想确认代码是否正常时，直接运行表格中的离线测试命令；这些测试不调用真实模型，例如：

```powershell
uv run python examples/lifecycle/test.py
```

AsyncSubAgent 的真实演示还需要先启动本地 Agent Server，具体步骤见对应目录的 README。

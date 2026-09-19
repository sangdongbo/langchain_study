# 专题示例

这个目录按功能保存可独立学习的 Deep Agents 示例。每个功能目录都有：

- `README.md`：原理、使用场景和详细说明。
- `run.py`：连接真实模型的演示入口。
- `test.py`：不需要 API Key 的离线测试。

| 目录 | 示例内容 | 真实演示命令 |
| --- | --- | --- |
| [async_subagent](async_subagent/README.md) | 通过 Agent Protocol 运行后台子 Agent | `uv run python examples/async_subagent/run.py` |
| [compiled_subagent](compiled_subagent/README.md) | 把预编译 Graph 作为子 Agent | `uv run python examples/compiled_subagent/run.py` |
| [declarative_subagent](declarative_subagent/README.md) | 声明式子 Agent 的 isolated/fork 模式 | `uv run python examples/declarative_subagent/run.py --mode isolated` |
| [dynamic_skills](dynamic_skills/README.md) | 根据身份和任务动态注入 Skill | `uv run python examples/dynamic_skills/run.py` |
| [lifecycle](lifecycle/README.md) | 观察普通 Agent 和子 Agent 生命周期 | `uv run python examples/lifecycle/run.py --kind agent` |

## 怎么启动

所有命令都从项目根目录执行：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
uv sync
```

真实演示需要先在 `.env` 中配置模型 API Key。只想确认代码是否正常时，运行各目录的 `test.py`，例如：

```powershell
uv run python examples/lifecycle/test.py
```

AsyncSubAgent 的真实演示还需要先启动本地 Agent Server，具体步骤见对应目录的 README。

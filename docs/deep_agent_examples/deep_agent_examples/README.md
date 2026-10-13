# 公共源码包

这个目录是整个示例项目共用的 Python 包，不是一个独立示例。

主要文件：

- `graphs.py`：定义 LangGraph Studio 和 CLI 使用的 11 个 Agent Graph。
- `cli.py`：提供 `deep-agent-example` 命令行入口。
- `config.py`：读取环境变量并创建模型。
- `tools.py`：提供采购场景的内存 Mock 工具。
- `lifecycle.py`：记录 Agent 生命周期事件。
- `cloud_sandbox.py`：运行 LangSmith 云沙箱示例。
- `testing.py`：各专题离线测试共用的 Fake Model。

## 怎么启动

先在项目根目录安装和配置：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
Copy-Item .env.example .env
uv sync
```

然后通过 CLI 选择一个示例，例如：

```powershell
uv run deep-agent-example tool
uv run deep-agent-example lifecycle
uv run deep-agent-example subagent
```

也可以一次启动全部 Graph，在 LangGraph Studio 中选择：

```powershell
uv run langgraph dev --host 127.0.0.1 --port 2024
```

具体示例和启动条件见上一级 [README.md](../README.md)。

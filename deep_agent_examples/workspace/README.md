# 本地 Shell 工作目录

这个目录是 `local_shell_agent` 的本地工作区。示例提示 Agent 只把文件写到 `artifacts/`，文件修改和命令执行都需要人工审批。

这只是本机开发演示，不是真正的安全沙箱。不要用它处理不可信输入，也不要部署到 Web API 或多租户环境。

## 在哪里使用

- [`deep_agent_examples/graphs.py`](../deep_agent_examples/graphs.py) 把 `WORKSPACE_DIR` 设置为本目录，并把它传给 `LocalShellBackend(root_dir=...)`。
- [`deep_agent_examples/cli.py`](../deep_agent_examples/cli.py) 在选择 `local-shell` 示例时创建这个 Agent，并使用 `InMemorySaver` 保存人工审批中断。
- 本文件只供人工阅读，程序不会加载它。

调用过程：

```text
CLI 选择 local-shell
  -> build_local_shell_agent(InMemorySaver())
  -> LocalShellBackend(root_dir=workspace, virtual_mode=True)
  -> Agent 请求写文件或执行命令
  -> interrupt_on 暂停，等待人工批准
  -> 批准后在本目录中执行操作
```

## 路径如何对应

`virtual_mode=True` 会把内置文件工具使用的虚拟路径映射到本目录：

| Agent 使用的虚拟路径 | 本机实际位置 |
| --- | --- |
| `/artifacts/hello.py` | `workspace/artifacts/hello.py` |
| `/artifacts/report.md` | `workspace/artifacts/report.md` |

`artifacts/.gitkeep` 没有运行功能。它只是让 Git 能够保留原本为空的 `artifacts` 目录。

需要注意：`virtual_mode=True` 只限制 Deep Agents 内置文件工具的路径映射，不能把任意 shell 命令限制在本目录。示例因此会在所有 `execute` 调用前中断并要求人工审核；这仍不能替代容器、虚拟机或云沙箱等真正的隔离环境。

## 怎么启动

在项目根目录执行：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
uv run deep-agent-example local-shell --approve --thread-id local-001
```

运行过程中会要求审批写文件和执行命令。成功后，生成的演示文件位于 [artifacts](artifacts/README.md)。

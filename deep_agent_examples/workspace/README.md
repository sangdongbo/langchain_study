# 本地 Shell 工作目录

这个目录是 `local_shell_agent` 的本地工作区。Agent 只能把示例文件写到 `artifacts/`，文件修改和命令执行都需要人工审批。

这只是本机开发演示，不是真正的安全沙箱。不要用它处理不可信输入，也不要部署到 Web API 或多租户环境。

## 怎么启动

在项目根目录执行：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
uv run deep-agent-example local-shell --approve --thread-id local-001
```

运行过程中会要求审批写文件和执行命令。成功后，生成的演示文件位于 [artifacts](artifacts/README.md)。

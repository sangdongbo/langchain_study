# OpenSandbox 独立示例

这个例子让 Deep Agent 在自托管 OpenSandbox 容器中创建并运行 `hello.py`，最后返回命令退出码。

它必须使用独立虚拟环境，因为当前 `langchain-opensandbox 0.1.0` 要求 `deepagents < 0.7`，与主项目使用的 `deepagents 0.7.x` 不兼容。

## 启动条件

1. 已启动可访问的 OpenSandbox Server。
2. 已在上一级 `.env` 配置模型 API Key。
3. 根据实际环境设置 `OPENSANDBOX_URL`、`OPENSANDBOX_API_KEY` 和 `OPENSANDBOX_IMAGE`。

## 怎么启动

在项目根目录执行：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples\optional_opensandbox
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

成功时会输出 Agent 在沙箱中创建、执行文件后的结果和退出码。脚本结束时会自动销毁本次创建的沙箱。

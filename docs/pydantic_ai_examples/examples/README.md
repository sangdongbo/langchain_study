# 按顺序学习

每个目录包含 `README.md`、真实模型演示 `run.py` 和离线检查 `test.py`。
所有命令从 `docs/pydantic_ai_examples/` 执行，安装步骤见[总览](../README.md)。

## 零基础先读哪里

先读[总览第 0 节：Pydantic 与 PydanticAI](../README.md)，认识数据校验库、Agent
框架和大语言模型的分工。下面八课分别增加一个能力，不需要提前掌握表里的全部 API。

| 学完这一课，你应该能回答 | 对应专题 |
| --- | --- |
| 谁生成回答？创建 Agent 与运行 Agent 有什么区别？ | 01 基础对话 |
| 怎样让程序拿到采购对象，而不是自己从回答里找数字？ | 02 结构化输出 |
| 模型怎样申请调用 Python 函数？可信租户信息放在哪里？ | 03 工具与依赖 |
| 数字和字段都合法，但采购结论错了，怎样让它修正？ | 04 校验与重试 |
| 下一轮怎样知道“单价不变”指的是什么？ | 05 多轮对话 |
| 怎样边生成边显示，避免重复拼接文字？ | 06 流式输出 |
| 一个 Agent 怎样调用另一个 Agent？怎样合计请求次数？ | 07 Agent 委派 |
| 怎样让模型只提出操作，人批准后才真正执行？ | 08 人工审批 |

## 每课怎么读

1. 先读本课 README 的问题和概念，再看代码执行过程。
2. 打开 `run.py`：先看 `build_agent()` 或 `build_agents()` 如何配置助手，再看
   `main()` 如何提供输入、发起运行和读取结果。
3. 运行 `test.py` 观察固定场景，再与 README 中的预期结果对照。
4. 最后运行 `run.py` 观察真实模型。它读取已有模型配置，会产生 API 用量。

`build_agent`、`build_agents`、`build_model` 都是本教程定义的普通 Python 函数，
不是框架要求的固定函数名。框架 API 是它们内部调用的 `Agent`、`run_sync`、`tool` 等。
第 07 课有父子两个 Agent，所以构造函数用了复数 `build_agents`。

`test.py` 使用 `assert` 检查真实结果，成功后打印 `PASS`；它既是检查程序，也可作为
离线演示。`TestModel` 返回预设响应，`FunctionModel` 用本地函数决定每一步模型响应。
它们不会验证真实模型的理解能力，但可以确定框架是否调用工具、执行校验、传递历史。

## 运行索引

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

第 04、07、08 课会故意制造失败。看到 `[已阻止]` 或 `[预期停止]`，最后仍输出该课
`PASS` 和 `ALL PASS`，说明保护规则按预期生效。如果出现未处理的 Traceback、没有
最终 `PASS` 或进程退出码非零，才需要检查失败原因。

PyCharm 的 Run 按钮运行的是顶部选定的运行配置，不一定是当前打开的文件。运行某课
前确认 Script path 指向该课的 `run.py` / `test.py`，解释器使用本示例的 `.venv`；
路径设置见[总览中的 PyCharm 说明](../README.md)。

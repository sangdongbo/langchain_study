# 01 · 基础 Agent

## 这一课解决什么问题

这一课只做一件事：给模型一条 instructions 和一个用户问题，取得文字结果。
`build_agent()` 定义行为，`run_sync()` 或 `await agent.run()` 执行一次运行，
`result.output` 是最终回答，`result.usage` 是框架累计的请求和 token 用量。

如果还不清楚 Pydantic 与 PydanticAI 的区别，先读[总览第 0 节](../../README.md)。
本课的目标是看懂“配置一个助手 → 问一个问题 → 读取结果”，暂时不加入工具和业务数据。

## 先理解这些概念

| 代码中的名字 | 含义 | 本课具体内容 |
| --- | --- | --- |
| `model` | 回答问题的模型接口；真实环境中连接外部模型服务 | `build_model()` 读取已有配置后创建 |
| `Agent` | 组织模型、指令和运行过程的助手对象 | 固定用简洁中文回答的教学助手 |
| `instructions` | 每次运行都要遵循的行为要求 | “你是 Python 教学助手。用简洁中文回答。” |
| `PROMPT` | 本次任务的问题；大写只是本教程的常量命名习惯 | “Agent 和普通聊天模型的区别是什么？” |
| `result` | 框架返回的运行结果对象 | 包含最终回答、用量和消息历史 |

`model` 与 `Agent` 是两层对象：模型生成内容，Agent 管理调用过程。本课只用文字问答，
后面会在相同的 Agent 上增加工具、结构化输出和校验。

函数签名中的 `Agent[None, str]` 是类型提示：第一个位置表示业务依赖类型，这里不需要，
所以写 `None`；第二个位置表示最终输出类型，这里是字符串 `str`。方括号不是传入用户
问题，真正的问题在 `run_sync(PROMPT)` 中传入。没有指定 `output_type` 时默认输出文字。

## 先用一个离线小例子认识 API

下面可直接粘贴到示例解释器的 Python Console，先理解核心步骤，再读完整的 `run.py`：

```python
from pydantic_ai import Agent, models
from pydantic_ai.models.test import TestModel

# 使用预设回答，并禁止真实模型请求，方便先观察运行结果对象。
models.ALLOW_MODEL_REQUESTS = False
agent = Agent(
    TestModel(custom_output_text="Agent 可以调用你提供的工具。"),
    instructions="用简洁中文回答。",
)
result = agent.run_sync("Agent 可以做什么？")
print(result.output)  # 输出上面预设的回答；本地测试模型没有理解或推理这句话。
print(result.usage.requests)  # 输出 1；这里是框架计数，没有网络请求。
```

这个 Console 中的禁请求开关会保留到该进程结束。后面的真实模型演示请通过独立的
`run.py` 进程运行；各课 `test.py` 也在自己的进程中设置开关。

## 对照 run.py 看执行过程

1. `main()` 用 `argparse` 读取终端参数；没有额外参数就使用默认问题。
2. `build_model()` 创建模型客户端，`build_agent(model)` 把它和 instructions 组合起来。
   这两个名字是本教程定义的函数，创建对象时尚未发出模型请求。
3. `agent.run_sync(...)` 开始运行，把问题交给模型并等待结果。
4. `print(result.output)` 显示回答，`print(result.usage)` 显示累计用量。

`if __name__ == "__main__"` 保证直接执行 `run.py` 时才进入 `main()`。`test.py`
可以导入这里的 `build_agent()`，替换为测试模型，而不会顺带启动真实模型演示。

## 怎样运行

从示例项目根目录运行：

```powershell
uv run python examples/01_basic_agent/test.py
uv run python examples/01_basic_agent/run.py
uv run python examples/01_basic_agent/run.py --async
uv run python examples/01_basic_agent/run.py --prompt "什么场景适合使用工具调用？"
```

`--prompt` 是本教程提供的命令行选项，用来替换本次用户问题；它不修改 instructions。
PyCharm 中可在 Script parameters 填写 `--async` 或 `--prompt "你的问题"`。

## 同步、异步和运行结果怎么看

`run_sync()` 会让当前调用等待整个任务完成，适合先用普通 Python 脚本学习。
`agent.run()` 是异步入口，需要写在 `async def` 定义的函数中，并用 `await` 等待结果。
异步允许等待模型时把执行机会让给其他任务，但本课没有同时发起多项任务，切换
`--async` 不等于自动并发或更快，也不改变输出类型。

先观察同步、异步两种写法的结果结构，再看 usage 中的 `requests`。一个 run 可以包含
多次模型请求；这里设置 `request_limit=3`，后面加入工具后会看到请求次数增加。
这个参数限制请求数量，不代表费用或 token 的精确上限。

在 Notebook 的已有事件循环中使用 `await agent.run(...)`，不要调用 `run_sync()`
或 `asyncio.run()`。当前 Python 文件中的 `asyncio.run()` 是终端入口的写法。

离线测试使用官方 `TestModel` 指定一条回答，同时验证同步与异步入口。它不证明真实
模型一定按 instructions 回答；下一课会让输出由 Pydantic 校验。

`test.py` 成功时显示 `01 PASS：同步、异步和 usage`。真实演示会先显示中文回答，再
显示 `usage:`；措辞和 token 数量可能变化。`result` 本身不是回答字符串，要读取
`result.output`。本项目锁定版本中的 `result.usage` 是属性，直接读取，不加 `()`。

下一步：[02 · 结构化输出](../02_structured_output/README.md)。

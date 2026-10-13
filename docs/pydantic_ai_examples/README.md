# PydanticAI：从入门到人工审批的可运行示例

参考同级 [Deep Agents 示例](../deep_agent_examples/README.md) 的组织方式，提供 8 个
逐步进阶的专题。每个专题都有真实模型 `run.py`、中文 `README.md` 和无需 API Key 的
离线 `test.py`。代码使用 PydanticAI **2.55.0**，依赖版本记录在 `uv.lock` 中。

业务数据使用内存字典，发布使用内存列表；没有数据库访问、文件删除、采购 API 或后台
服务。真实演示只向配置的模型接口发送请求，离线检查使用官方测试模型。

## 1. 安装并先跑离线演示

```powershell
cd D:\PythonProject\LearnOne\docs\pydantic_ai_examples
if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }
$env:PYTHONUTF8 = "1"
$env:PYTHONIOENCODING = "utf-8"
$env:PYDANTIC_AI_NO_BANNER = "1"
uv sync --locked
uv run --frozen python scripts_smoke.py
```

需要 Python 3.11+ 与 uv。这个目录拥有独立 `.venv`，不会把 PydanticAI 安装到 Deep
Agents 或仓库主项目的环境。使用 `pydantic-ai-slim[openai]`，只安装当前演示需要的
模型供应商依赖。

`uv sync` 首次安装需要访问包索引；依赖就绪后，`scripts_smoke.py` 中的 Python 检查
不发出网络请求。输出应包含 `01 PASS` 到 `08 PASS`，以及配置检查通过。
各 `test.py` 同时也是可以在无 Key 环境演示框架行为的小程序。

共享包的职责、配置加载细节与离线检查方式见 [pydantic_examples 说明](pydantic_examples/README.md)。

## 2. 使用已经存在的 .env

无需为了本例复制已有密钥。`build_model()` 加载以下文件，同名变量先到先得：

1. 本目录 `.env`。
2. 仓库根目录 `../../.env`。
3. 参考项目 `../deep_agent_examples/.env`，作为补充。

进程环境中的同名变量不会被文件覆盖。加载后按 `LLM_API_KEY` →
`DEEPSEEK_API_KEY` → `OPENAI_API_KEY` 选择第一个非空凭据，每个凭据只读取同一前缀
的 `*_BASE_URL` 和 `*_MODEL`。这两个优先级分别处理「同名配置来源」和「供应商选择」。

DeepSeek 未指定地址或模型时使用 `https://api.deepseek.com/v1`、`deepseek-chat`；
LLM/OpenAI 未指定时使用 OpenAI 官方地址和 `gpt-4o-mini`。
例如已有 DeepSeek Key 时，不会把其他前缀的 OpenAI 地址拼到它上面。

如果已有本目录 `.env`，直接使用它；更换模型时编辑其中的配置。仅首次需要时创建：

```powershell
if (-not (Test-Path -LiteralPath .env)) { Copy-Item -LiteralPath .env.example -Destination .env }
```

修改 `.env` 中的 `LLM_API_KEY`、`LLM_BASE_URL`、`LLM_MODEL`，使用支持 Chat Completions
和工具调用的模型。不要提交真实 `.env`；示例只提交无密钥的 `.env.example`。
配置缺失会在运行入口报错，不会在导入教学代码时调用模型。
上面的命令不会覆盖已有密钥。`.env` 中的 `PYTHONUTF8` / `PYTHONIOENCODING` 在
Python 启动后加载不能改变终端编码，Windows 演示仍需先设置第 1 节的进程环境变量。

## 3. 学习与演示顺序

| 课 | 主题 | 重点观察 | 实际演示 |
| --- | --- | --- | --- |
| [01](examples/01_basic_agent/README.md) | 基础 Agent | 同步/异步入口、`result.output`、`result.usage` | `uv run python examples/01_basic_agent/run.py` |
| [02](examples/02_structured_output/README.md) | 结构化输出 | Pydantic 对象、字段约束、总额 272000 元 | `uv run python examples/02_structured_output/run.py` |
| [03](examples/03_tools_and_deps/README.md) | 工具与依赖 | 总额计算、租户预算、缺口 4000 元 | `uv run python examples/03_tools_and_deps/run.py` |
| [04](examples/04_validation_retry/README.md) | 校验与重试 | 错误结论修正、重试耗尽、请求上限 | `uv run python examples/04_validation_retry/run.py` |
| [05](examples/05_message_history/README.md) | 消息历史 | 第二轮只修改数量、JSON 历史恢复 | `uv run python examples/05_message_history/run.py` |
| [06](examples/06_streaming/README.md) | 流式输出 | 增量打印、完整结果、最终用量 | `uv run python examples/06_streaming/run.py` |
| [07](examples/07_agent_delegation/README.md) | Agent 委派 | 父子调用、类型化子结果、共用请求预算 | `uv run python examples/07_agent_delegation/run.py` |
| [08](examples/08_human_approval/README.md) | 人工审批 | 暂停时零执行、批准/修改/拒绝、恢复 | `uv run python examples/08_human_approval/run.py` |

只运行某个离线专题，把命令中的 `run.py` 换成 `test.py`。
详细命令与原理见[专题索引](examples/README.md)和各课 README。

适合现场演示的顺序：先用第 02 课把自然语言变成对象，再用第 03 课看工具结果，接着
运行第 04 课的 `test.py` 观察确定性的错误修正，最后演示第 08 课的三个审批决策。
真实模型可能第一次就答对、改变工具选择或措辞，因此预期数字与业务边界比固定回答文本
更适合作为观察标准。

## 4. 与 Deep Agents 对照

| 学过的概念 | 本套 PydanticAI 示例 | 边界 |
| --- | --- | --- |
| 普通工具调用 | `@agent.tool_plain`、`@agent.tool` | 由参数类型和 Field 生成 schema |
| Runtime Context | `deps_type`、`RunContext.deps` | 依赖由调用方提供，授权仍由工具实施 |
| 结构化结果 | `output_type=BaseModel` | schema 校验与业务事实校验分别实现 |
| 工具/输出修正 | `ModelRetry`、`output_validator` | 不等同于网络故障重试 |
| 多轮 State | 显式 `message_history` | 不是 LangGraph checkpoint |
| Streaming | `run_stream`、`stream_text` | 文字流不包含所有工具/节点事件 |
| 同步子任务委派 | 在父工具内 `await child.run()` | 同进程执行，未实现远程后台任务 |
| HITL | `DeferredToolRequests` 与 `DeferredToolResults` | 以工具调用 ID 对应人工决定 |

PydanticAI 2.x 的普通运行结果用 `result.usage` 属性；不要照搬旧版本的
`result.usage()`，也不要把旧教程的 `result.data` 用于这里。
本套聚焦核心 Agent 机制，未实现 Deep Agents 的 Skills、虚拟文件系统、沙箱、完整
生产持久化，也不宣称覆盖 PydanticAI 的全部能力。

## 5. 常见问题

- 找不到 `pydantic_examples`：确认从本项目根目录执行 `uv sync --locked` 后使用
  `uv run`；不要用其他项目的 Python 环境直接运行。
- 没有模型 Key：先跑 `test.py`，或按上面的配置来源检查密钥变量是否非空。
- 401 / 404：核对同一供应商的 Key、地址和模型名；错误信息不应附带密钥。
- 工具调用/结构化输出不支持：使用支持 function calling 的 Chat Completions 模型。
- Windows 中文乱码：在启动 Python 前设置上面的 `PYTHONUTF8` 和 `PYTHONIOENCODING`。
- 第 08 课没有暂停：检查模型是否提出了 `publish_review` 调用；程序会明确报告未进入
  审批，而不会伪造一次人工审批。

真实演示会发送样例输入到所配置的模型服务并产生 API 用量。第 07 课包含父子请求，
第 08 课包含暂停和恢复两个阶段；所有入口设置请求上限，但这不等于精确的费用上限。
第 08 课已批准工具可能在后续模型请求失败前执行；不要因最后的汇总失败就直接重试提交。

## 6. 验证记录

2026-10-13，使用本项目独立环境（Python 3.14.2、PydanticAI 2.55.0）验证。
真实调用通过已有 `.env` 配置的 DeepSeek `deepseek-chat` 完成，密钥未写入日志或文档。

`scripts_smoke.py` 的配置检查和 8 个离线专题全部通过。真实模型验证结果如下：

| 专题 | 实际观察结果 |
| --- | --- |
| 01 基础 Agent | 同步和 `--async` 入口均返回中文回答及用量 |
| 02 结构化输出 | 返回采购对象，4 × 68000 = 272000 元 |
| 03 工具与依赖 | 实际调用总额与预算工具，预算 268000 元、缺口 4000 元 |
| 04 校验与重试 | 实际触发业务校验，首次 `reject` 通过；错误修正与上限由离线测试验证 |
| 05 消息历史 | JSON 历史恢复后，把数量改为 6 台，沿用单价得出 408000 元 |
| 06 流式输出 | 文字增量输出，随后取得完整结果和用量 |
| 07 Agent 委派 | 父工具调用子 Agent，返回缺口 4000 元，再完成汇总，合计 3 次请求 |
| 08 人工审批 | 三条路径暂停时均为 0 条记录；批准写入 272000 元、修改写入 268000 元、拒绝仍为空 |

第 08 课调整工具返回说明后，重新验证了三条真实路径：修改金额被解释为人工审批调整，
不再误报为发布错误。三条路径各使用 2 次模型请求，最终以内存列表记录为准。

后续完善仅做离线回归，未再次付费调用：补充了单笔审批限制、非法修改参数、共享请求
上限及入口停止边界的检查；所有 8 个专题通过。还检查了配置文件加载顺序、Python 3.11
语法兼容性和本地 Markdown 链接，初始化 `.env` 的命令改为不覆盖已有文件。

这是一轮实际运行记录，不是对所有模型、未来版本或每次回答的保证。离线测试用于稳定
复现框架流程与失败边界；真实演示的措辞、工具选择和用量可能变化。

## 7. 官方参考

- [Agent](https://ai.pydantic.dev/agents/)
- [结构化输出](https://ai.pydantic.dev/output/)
- [依赖注入](https://ai.pydantic.dev/dependencies/)
- [工具](https://ai.pydantic.dev/tools/)
- [消息历史](https://ai.pydantic.dev/message-history/)
- [测试模型](https://ai.pydantic.dev/testing/)
- [多 Agent](https://ai.pydantic.dev/multi-agent-applications/)
- [延迟工具与人工审批](https://ai.pydantic.dev/deferred-tools/)

官方文档会随版本更新；本套代码以 `pyproject.toml` 和 `uv.lock` 中的版本为准。

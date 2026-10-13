# Browser Agent 可运行示例

学过 LangGraph 和 Deep Agents 后，这组练习把重点放在「Agent 如何观察网页、执行动作、
判断任务是否完成」。每节都有中文 `README.md`、可直接运行的 `run.py` 和无需模型 Key
的 `test.py`，目录结构参考 `deep_agent_examples`。

前 3 节学习 Playwright，后 2 节使用真实 browser-use Agent。第 05 节用 **Pydantic**
约束输出；它没有使用 PydanticAI 的 `Agent`，PydanticAI 的课程在相邻目录单独学习。

## 学习路线

| 阶段 | 运行时会看到什么 | 核心知识 |
| --- | --- | --- |
| [01 基础](examples/01_playwright_basics/README.md) | 打开商城，读取 6 个商品，保存截图 | 页面导航、Locator、内容提取 |
| [02 表单](examples/02_forms_and_waiting/README.md) | 填写表单，等待异步更新，只留下笔记本 | 输入、选择、断言、Trace |
| [03 会话](examples/03_session_state/README.md) | 登录后关闭旧上下文，新上下文直接进入控制台 | `storage_state`、localStorage、上下文隔离 |
| [04 Agent](examples/04_browser_use_agent/README.md) | 给模型一个筛选目标，由它选择网页动作 | 观察 → 决策 → 动作 → 再观察 |
| [05 研究](examples/05_structured_research/README.md) | 跨商品详情页读取信息，输出并验收 JSON | 输出 schema、来源、事实与轨迹校验 |

从 [examples/README.md](examples/README.md) 按 01–05 顺序运行。页面使用同一份固定商品
数据，无需准备真实网站、账号或数据库。脚本自动在 `127.0.0.1` 的随机端口启动静态
服务器，结束时关闭服务器和浏览器。

## 安装与第一场演示

需要 [uv](https://docs.astral.sh/uv/getting-started/installation/) 和 Python 3.11+。
建议选择本项目验证过的 Python 3.12。以下命令均在本目录执行：

```powershell
cd D:\PythonProject\LearnOne\docs\browser_agent_examples
uv sync --python 3.12 --locked
uv run playwright install chromium

# 不需要模型 Key：显示浏览器，结束后按 Enter 关闭
uv run python examples/01_playwright_basics/run.py --pause
uv run python examples/02_forms_and_waiting/run.py --pause
uv run python examples/03_session_state/run.py --pause
```

依赖和虚拟环境独立于仓库其他项目。版本已锁定为 browser-use 0.13.11、Playwright
1.63.0、Pydantic 2.13.5，`uv.lock` 保留了完整依赖版本。首次安装需要下载依赖和浏览器。
所有 `run.py` 都支持 `--headless`；01–03 的 `--pause` 只在有窗口时生效。

## 配置模型并运行 Agent

仅 04–05 的 `run.py` 会调用真实模型。首次配置时复制模板，已有 `.env` 时直接编辑：

```powershell
Copy-Item .env.example .env
```

例如使用 DeepSeek，填写这一组，其余 Key 留空：

```dotenv
DEEPSEEK_API_KEY=你的密钥
DEEPSEEK_BASE_URL=https://api.deepseek.com/v1
DEEPSEEK_MODEL=deepseek-chat
```

也可填写 `LLM_API_KEY/LLM_BASE_URL/LLM_MODEL`，接入兼容 OpenAI 协议的服务，或填写
`OPENAI_*`。Key 组的选择优先级是 `LLM_* → DEEPSEEK_* → OPENAI_*`。已有进程环境变量
优先；随后依次补充本目录 `.env`、仓库根目录 `.env`、`deep_agent_examples/.env` 中缺少
的变量。独立演示时，建议把完整的一组配置填写在本目录，避免继承到不同模型。

```powershell
uv run python examples/04_browser_use_agent/run.py
uv run python examples/05_structured_research/run.py

# 不显示窗口，显式限制模型步骤
uv run python examples/04_browser_use_agent/run.py --headless --max-steps 12
uv run python examples/05_structured_research/run.py --headless --max-steps 20
```

这里使用 browser-use 自带的 `ChatOpenAI`，并设置 `use_vision=False`：模型根据页面 DOM
文本决策，不要求视觉模型。对兼容接口使用「在提示中提供 schema，再解析返回 JSON」
的方式，避免要求服务实现 OpenAI 严格 `json_schema`。兼容协议不代表所有模型都有同样
的网页操作与 JSON 输出能力，具体效果需要用自己的模型实测。

browser-use 负责启动 Playwright 下载的 Chromium 并通过 CDP 控制它；它没有调用第 02
节的固定脚本。浏览器导航限定在 `127.0.0.1`，Agent 限制最大步骤和连续失败次数。
模型服务仍需网络连接，且按服务商规则计费。

## 结果与回看

所有生成文件位于已被 Git 忽略的 `.artifacts/`：

| 示例 | 生成文件 | 用途 |
| --- | --- | --- |
| 01 | `01_playwright_basics/page.png` | 查看完整商品目录 |
| 02 | `02_forms_and_waiting/page.png`、`trace.zip` | 查看筛选结果和操作前后页面 |
| 03 | `auth.json` | 检查保存的浏览器状态 |
| 04 | `04_browser_use_agent/<run-id>/history.json`、`conversation/`、`status.json` | 回看一次运行的页面、模型响应和状态 |
| 05 | `05_structured_research/<run-id>/history.json`、`conversation/`、`status.json`、成功时的 `result.json` | 回看一次研究及通过验收的 JSON |

回看第 02 节的操作轨迹：

```powershell
uv run playwright show-trace .artifacts/02_forms_and_waiting/trace.zip
```

04–05 预期找到「数据分析笔记本 5999 元」和「开发者迷你主机 4299 元」。04 展示自由
文本结果；05 还要求访问两张详情页，并检查漏项、重复、价格、原文、来源 URL 和访问
记录。Agent 日志中的“成功”是模型的完成声明，不能替代这些外部检查。

04–05 每次启动都会创建带时间和随机后缀的 `<run-id>` 目录，终端会打印本次目录。
`status.json` 从 `running` 更新为 `success` 或 `failed`；失败目录保留已有轨迹，但不会
生成 `result.json`。因此后一次失败不会让前一次成功的结果看起来像本次结果。

## 不用模型 Key 的验证

```powershell
# 仅解析 Python 语法并检查教学文件完整性，不启动浏览器
uv run python scripts_smoke.py

# 真实启动本地 Chromium，不请求模型 API
uv run python examples/01_playwright_basics/test.py
uv run python examples/02_forms_and_waiting/test.py
uv run python examples/03_session_state/test.py
uv run python examples/04_browser_use_agent/test.py
uv run python examples/05_structured_research/test.py
```

04–05 使用 `ScriptedModel` 返回预先指定的动作，但会从完整 `run_demo()` 入口运行真实
浏览器，并检查成功/失败状态、轨迹和结果文件。浏览器连接、动作执行、页面读取和
schema 处理都是真实流程。这不能证明真实模型能自主规划任务，也不能用固定动作的
步骤数估算真实模型成本。

## 常见问题

| 现象 | 处理方式 |
| --- | --- |
| 找不到 Chromium | 在本目录执行 `uv run playwright install chromium` |
| 导入 `browser_examples` 失败 | 先执行 `uv sync --python 3.12 --locked`，从本目录用 `uv run` 运行 |
| 窗口很快关闭 | 01–03 加 `--pause`，02 也可回看 Trace |
| 401、403 或模型不存在 | 检查生效的 Key 组、`BASE_URL` 和 `MODEL` 是否属于同一服务 |
| 模型未返回有效 JSON | 打开终端打印的本次目录，查看 `conversation/` 和 `status.json` |
| 达到步数或输出验收失败 | 查看本次目录的 `history.json` 和 `status.json`；确定原因后再调整提示或步数 |
| 会话文件在下次演示不生效 | 每次启动使用随机端口；第 03 节只演示同一次启动内的上下文复用 |

## 继续练习

先把第 02 节关键词改成 `内存`，分析为什么会多出迷你主机；再修改第 04 节自然语言
任务，观察模型是否找到同样结果。第 05 节的验收规则针对固定任务，改变价格预算或
商品数据时需要同步修改验收与测试。

官方资料：[Playwright Python](https://playwright.dev/python/docs/intro)、
[Trace Viewer](https://playwright.dev/python/docs/trace-viewer)、
[browser-use](https://docs.browser-use.com/)、
[Pydantic](https://docs.pydantic.dev/latest/)。

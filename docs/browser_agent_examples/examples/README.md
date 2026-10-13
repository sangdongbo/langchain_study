# 按顺序学习

每个目录都有中文说明、可运行的 `run.py` 和不调用模型的 `test.py`。

| 顺序 | 专题 | 新增知识 | 演示命令 |
| --- | --- | --- | --- |
| 1 | [Playwright 基础](01_playwright_basics/README.md) | 启动浏览器、导航、Locator | `uv run python examples/01_playwright_basics/run.py` |
| 2 | [表单与等待](02_forms_and_waiting/README.md) | 输入、选择、点击、自动等待 | `uv run python examples/02_forms_and_waiting/run.py` |
| 3 | [会话状态](03_session_state/README.md) | 登录、`storage_state`、上下文隔离 | `uv run python examples/03_session_state/run.py` |
| 4 | [browser-use Agent](04_browser_use_agent/README.md) | 目标驱动操作、步数与域名边界 | `uv run python examples/04_browser_use_agent/run.py` |
| 5 | [结构化网页研究](05_structured_research/README.md) | browser-use + Pydantic 输出契约 | `uv run python examples/05_structured_research/run.py` |

所有命令从 `docs/browser_agent_examples` 执行，先完成[安装与模型配置](../README.md)。

01–03 的 `run.py` 不需要 Key；04–05 的 `run.py` 使用真实模型。所有 `test.py` 都会
启动本地 Chromium，04–05 用固定模型响应验证 browser-use 接口，不请求模型 API。
所有示例只使用本地演示商城。

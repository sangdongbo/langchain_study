# 01 Playwright 基础

这一节先建立可预测的浏览器操作流程：启动本地静态商城，打开 Chromium，读取商品
名称并保存截图。不需要模型 Key。代码见 [run.py](run.py)。

## 运行与观察

先按[根目录说明](../../README.md)安装依赖。所有命令从 `docs/browser_agent_examples`
执行，后续各节也遵循这一约定。

```powershell
uv run python examples/01_playwright_basics/run.py --pause
uv run python examples/01_playwright_basics/run.py --headless
uv run python examples/01_playwright_basics/test.py
```

浏览器显示 6 个商品；终端输出标题和商品名称：

```text
页面标题： Browser Agent 演示商城
商品名称： AI 推理工作站、数据分析笔记本、开发者迷你主机、4K 显示器、机械键盘、Agent 工程课程
```

截图保存在 `.artifacts/01_playwright_basics/page.png`。`--pause` 在完成后等你按 Enter，
适合讲解；`--headless` 适合自动检查，仍然会生成截图。

## 读懂代码

1. `DemoServer()` 自动启动仅本机可访问的静态服务器，退出时关闭。
2. `sync_playwright()` 创建控制入口，`chromium.launch()` 启动浏览器。
3. `browser.new_page()` 创建页面，`page.goto()` 导航到商城。
4. `expect(...).to_have_count(6)` 确认列表已渲染，再用 `all_text_contents()` 读取名称。
5. `page.screenshot()` 保存最终画面，`browser.close()` 释放浏览器。

Locator 是对元素的查询描述；使用时再解析到当前页面元素。真实项目优先使用
`get_by_role()`、`get_by_label()`、`get_by_test_id()`，CSS 适合同类列表读取。不要把
`all_text_contents()` 当作等待工具：这里先用可重试的断言确认列表就绪。

## 小练习

把 `page.locator('.product h2')` 改成 `page.get_by_role('heading', level=2)`，确认读取
结果一致，再尝试读取商品价格。[test.py](test.py) 会真实打开无窗口浏览器并检查商品
数量与关键名称。

下一节：[表单与等待](../02_forms_and_waiting/README.md)。

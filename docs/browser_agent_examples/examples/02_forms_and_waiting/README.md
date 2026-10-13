# 02 表单与等待

在第 01 节的商城中填写筛选条件：关键词 `32GB`、分类「计算设备」、最高价 `6500`。
页面模拟 300ms 异步更新，演示如何围绕结果状态等待。代码见 [run.py](run.py)，不需要
模型 Key。

## 运行

从 `docs/browser_agent_examples` 执行：

```powershell
uv run python examples/02_forms_and_waiting/run.py --pause
uv run python examples/02_forms_and_waiting/run.py --headless
uv run python examples/02_forms_and_waiting/test.py
```

页面先显示「正在筛选…」，最后显示「找到 1 件商品」，只剩 **数据分析笔记本，5999
元**。AI 推理工作站虽有 32GB 内存，价格超过预算；迷你主机只有 24GB，不匹配关键词。

## 读懂代码

1. `get_by_test_id('keyword').fill('32GB')` 填写文本，`select_option()` 选择分类。
2. `.click()` 点击筛选按钮；它会等待按钮可操作，但不代表异步结果已完成。
3. `expect(result_status).to_have_text('找到 1 件商品')` 持续重试，直到业务状态就绪。
4. `.product:visible` 只读取筛选后可见的商品。

这里没有固定 `sleep()`。页面条件决定等待何时结束，加载变慢时更容易定位失败原因。
固定流程用 Playwright 写清动作和完成断言，后续再与 Agent 的动态决策进行比较。

## 回看操作轨迹

输出位于 `.artifacts/02_forms_and_waiting/`：`page.png` 是最终画面，`trace.zip` 包含
动作、截图和 DOM 快照。

```powershell
uv run playwright show-trace .artifacts/02_forms_and_waiting/trace.zip
```

在 Trace Viewer 中点击 `fill`、`select_option` 和 `click`，对比操作前后的页面。
[test.py](test.py) 会打开真实浏览器并验证最终结果只有笔记本。

## 小练习

将关键词改为 `内存`，此时笔记本与迷你主机都符合条件，状态和断言也需要改成 2 件。
如果只改输入而没有改预期，观察断言如何报告失败。

下一节：[会话状态](../03_session_state/README.md)。

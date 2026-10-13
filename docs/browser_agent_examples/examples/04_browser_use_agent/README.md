# 04 browser-use Agent

前三节在代码中明确每一步；这一节给出自然语言任务，让 browser-use Agent 根据页面
状态选择输入、点击和读取动作。代码见 [run.py](run.py)。

## 运行

先按[根目录说明](../../README.md#配置模型并运行-agent)配置 `.env`，然后从
`docs/browser_agent_examples` 执行：

```powershell
uv run python examples/04_browser_use_agent/run.py
uv run python examples/04_browser_use_agent/run.py --headless --max-steps 12
```

无需模型 Key 的集成检查，仍会启动真实浏览器：

```powershell
uv run python examples/04_browser_use_agent/test.py
```

## 任务和预期结果

`build_task()` 要求 Agent 选择「计算设备」，设置最高价为 6500，点击筛选，读取所有
可见商品。没有关键词条件，所以应找到：

| 商品 | 价格 |
| --- | --- |
| 数据分析笔记本 | 5999 元 |
| 开发者迷你主机 | 4299 元 |

这是与第 02 节的差别：第 02 节额外输入 `32GB`，所以只有笔记本。模型回答的措辞和
具体动作次序可能不同，商品与价格应保持一致。

## Agent 的运行循环

```text
任务 + 当前页面 DOM
  → 模型选择动作
  → browser-use 执行输入、点击、导航或读取
  → 更新页面状态和动作结果
  → 模型继续决策，或声明 done
```

`build_agent()` 连接三个部分：任务、browser-use 自带的 `ChatOpenAI`、本地
`BrowserSession`。`use_vision=False` 让模型基于文本工作；`use_judge=False` 和
`enable_planning=False` 关闭额外评审与规划调用，先观察最基本的操作循环。

这里没有用 LangGraph 再包装一层流程；browser-use 已经提供了观察与动作循环。
Playwright 只提供已安装浏览器的路径，实际动作由 browser-use 通过 CDP 执行。

## 怎么回看与判断成功

观察终端中的 `Step`、`Next goal`、动作及最终结果。每次运行创建独立的
`.artifacts/04_browser_use_agent/<run-id>/`，终端会打印实际路径，其中包含：

- `history.json`：页面、动作、结果和错误。
- `conversation/`：模型看到的上下文与返回的动作。
- `status.json`：本次运行的 `running`、`success` 或 `failed` 状态。

`max_steps` 控制运行步数，`max_failures=2` 限制连续失败，`llm_timeout=60` 限制单次
模型调用等待时间；步数不是费用上限，SDK 重试也可能增加请求。浏览器导航限定在
`127.0.0.1`。结束后在 `finally` 中关闭浏览器，再关闭本地服务器。

脚本会拒绝没有结果或没有成功完成声明的运行，但“Agent 自报成功”仍不足以证明
商品事实正确。请先按上表人工核对；第 05 节会演示独立结果验收。

[test.py](test.py) 从完整 `run_demo()` 入口运行成功和失败两次，用固定的 `evaluate`
和 `done` 响应验证真实连接、异步筛选、页面数据、独立轨迹及状态文件。它覆盖代码
集成，不评估模型是否能自己识别下拉框或规划步骤。

## 小练习

给任务加上“关键词 32GB”，与第 02 节的结果比较。再把预算改成 7000，预测会新增
哪个商品，然后运行验证。任务中的 URL 单独成行，避免 URL 自动识别把中文标点也
拼进路径。

下一节：[结构化网页研究](../05_structured_research/README.md)。

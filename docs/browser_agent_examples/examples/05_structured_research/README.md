# 05 结构化网页研究

这一节从「回答文字」进到「输出可交给后续程序的数据」。browser-use 负责跨页面
浏览，Pydantic 负责字段校验，固定练习的验收函数负责核对事实与访问记录。代码见
[run.py](run.py)。使用的是 Pydantic 数据模型，没有使用 PydanticAI 的 `Agent`。

## 运行

先配置[模型 Key](../../README.md#配置模型并运行-agent)，从 `docs/browser_agent_examples`
执行：

```powershell
# 需要模型 Key
uv run python examples/05_structured_research/run.py
uv run python examples/05_structured_research/run.py --headless --max-steps 20

# 字段/事实校验 + 固定响应驱动真实浏览器，不请求模型 API
uv run python examples/05_structured_research/test.py
```

## 多页面任务

Agent 先在商品列表中找出预算 6500 元内的计算设备，再分别访问笔记本和迷你主机的
详情页，原样记录规格与使用说明、保留来源 URL，最后给出一句推荐。

```text
商品列表
  → 笔记本详情页：名称、价格、规格、使用说明、URL
  → 迷你主机详情页：同样字段
  → ResearchResult
  → 固定数据 + 浏览轨迹验收
  → <run-id>/result.json
```

模型可以返回目录再打开下一张详情，也可以直接导航；重点是两张来源页实际出现在
浏览记录中，不强制动作顺序。

## 输出契约

`Product` 定义非空名称、正整数价格、非空规格、详情说明和来源 URL；`ResearchResult`
定义需求、商品列表和推荐。`extra='forbid'` 拒绝未定义字段。把这个模型传给
`Agent(output_model_schema=ResearchResult)`，成功后从 `history.structured_output` 获取
Pydantic 对象，无需自行截取模型回答中的 JSON。

一次合格结果的形状如下。端口仅为示意，实际每次随机生成，推荐文本也可能不同：

```json
{
  "requirement": "计算设备且不超过 6500 元",
  "products": [
    {
      "name": "数据分析笔记本",
      "price_yuan": 5999,
      "specs": "32GB 内存 · 1TB SSD",
      "details": "便携机型，适合移动办公与数据分析。",
      "source_url": "http://127.0.0.1:8765/detail.html?id=laptop"
    },
    {
      "name": "开发者迷你主机",
      "price_yuan": 4299,
      "specs": "24GB 内存 · 512GB SSD",
      "details": "桌面机型，适合固定工位；不含显示器。",
      "source_url": "http://127.0.0.1:8765/detail.html?id=mini"
    }
  ],
  "recommendation": "固定工位且预算优先时选择开发者迷你主机。"
}
```

## 类型正确与事实正确

| 检查层 | 本节检查什么 | 能否独立证明任务完成 |
| --- | --- | --- |
| Agent 完成声明 | `history.is_successful()` | 不能，是模型自报 |
| Pydantic | 字段、类型、长度、正数、额外字段 | 不能，虚构信息也可能符合类型 |
| 固定任务验收 | 恰好两个商品、无重复、价格、规格与说明原文、正确 URL | 能核对本练习的商品事实 |
| 访问记录 | 两张详情页都在 `history.urls()` 中 | 能核对浏览经过，但不能证明所有语义理解 |

`validate_demo_result()` 用本地固定数据作为答案，而非再次询问模型。它故意要求原文
一致，让幻觉、错价和漏项容易复现。改变商品、预算或任务时，必须同步修改验收规则
和测试；该函数不是任意网站都能使用的通用评审器，也不评价推荐文本是否最优。

## 产物与排错

每次运行创建独立的 `.artifacts/05_structured_research/<run-id>/`，终端会打印实际路径。
脚本先保存 `history.json`，再做验收；只有通过后才在本次目录写入 `result.json`。
`conversation/` 保存每步模型上下文和响应，`status.json` 标记 `running`、`success` 或
`failed`。失败不会删除旧的成功记录，也不会在失败目录留下容易误认的旧结果。

如果字段无效，先看模型返回格式；如果商品事实不符，查看哪一页没有读到、是否漏项；
如果访问记录不符，检查 Agent 是否只在列表页生成了一个看似正确的详情 URL。
只有提高 `--max-steps` 无法解决这些问题，需要根据轨迹定位原因。

[test.py](test.py) 验证负价格、漏项、重复、错误原文/URL和未访问来源的拒绝行为，
再从完整 `run_demo()` 入口验证成功与事实验收失败。成功路径用固定模型动作真实访问
两个详情页；测试还检查两次运行目录隔离、状态、轨迹，以及失败目录没有 `result.json`。

## 小练习

先在测试中把一个 `price_yuan` 改成 1：它仍是合法正整数，但事实验收会拒绝。
再把 `source_url` 改成另一商品的 URL，区分「字符串合法」与「来源正确」。
掌握这一节后，再考虑给真实研究任务增加抓取时间、证据片段和一组固定评估案例。

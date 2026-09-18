# 声明式 SubAgent：isolated、fork 与 State 传播

声明式 `SubAgent` 是一份由 Deep Agents 在父 Graph 构建期间编译的子 Agent 配置。它适合角色明确、工具范围较小、无需复用现成 Graph 的同步委托。

对应文件：

- 真实模型与 LangSmith：[examples/declarative_subagent.py](examples/declarative_subagent.py)
- Fake Model 测试：[examples/test_declarative_subagent.py](examples/test_declarative_subagent.py)

## 1. 最小结构

```python
risk_reviewer: SubAgent = {
    "name": "risk-reviewer",
    "description": "Checks inventory, supplier, and delivery risk.",
    "model": model,
    "tools": [check_inventory, check_supplier],
    "mode": "isolated",
    "system_prompt": "Use tools and return risks with evidence.",
}

parent = create_deep_agent(
    model=model,
    tools=[calculate_total, check_budget],
    subagents=[risk_reviewer],
)
```

父 Agent 不会直接调用子 Agent 对象，而是获得统一的 `task` 工具。模型产生的调用类似：

```json
{
  "name": "task",
  "args": {
    "description": "检查 4 台 AI 推理服务器的库存和供应商风险，返回证据。",
    "subagent_type": "risk-reviewer"
  }
}
```

`description` 是子 Agent 的任务输入，不只是日志标题。在 isolated 模式中，没有写进 description 的父对话细节，子 Agent通常看不到。

## 2. 构建与运行生命周期

```text
create_deep_agent(parent)
  │
  ├─ 校验 SubAgent name / mode
  ├─ 用 SubAgent.model、tools、middleware 编译 child runnable
  ├─ 建立 name -> runnable 映射
  └─ 给父 Agent 注册 task 工具
  │
  ▼
父模型调用 task
  │
  ├─ 根据 subagent_type 选 child runnable
  ├─ 从父 State 构造 child State
  ├─ child.invoke / child.ainvoke（父调用等待）
  ├─ 取得 structured_response 或最后一个非空 AIMessage
  ├─ 转成父消息流中的 ToolMessage
  └─ 把允许回传的公共 State 字段合并回父 State
  │
  ▼
父 Agent 继续下一轮模型调用
```

“在构建时编译”不代表子 Agent 在后台常驻。真正的 child run 只在 `task` 被调用时创建；同步 `task` 会等待它完成。

## 3. 默认 isolated 模式

isolated 不是“完全没有任何父 State”，而是专门重建 `messages`：

```text
父 messages ────────────────X 不直接传入
task.description ──────────> child HumanMessage
父公共自定义 State ────────> child State（前提是 schema 接受）
父私有 Middleware State ───X 被过滤
```

构造 child State 时会排除：

- `messages`
- `todos`
- `structured_response`
- fork 内部标记
- 标记为 `PrivateStateAttr` 的字段

随后把 `messages` 设为只包含委托 description 的新列表。其他公共字段可以传入，但 child Graph 必须声明兼容的 State schema，否则字段不会成为它的有效 State channel。

isolated 的价值：

- 控制上下文长度。
- 减少无关父对话干扰。
- 降低敏感上下文泄露范围。
- 强迫父 Agent 写出完整、可审计的委托描述。

代价是父 Agent 如果漏掉金额、ID、截止时间或输出格式，子 Agent 无法自动补齐。

## 4. 实验性 fork 模式

`mode="fork"` 会把父 Agent 的有效对话和更多 State 带入 child：

```text
父有效 messages
  -> 应用当前 summarization event
  -> 移除末尾触发 task 的 AI tool-call message
  -> 追加带 fork 说明的委托 HumanMessage
  -> child messages
```

声明式 fork 还会继承父 Graph 的更多上下文，并重建相应的 prompt-producing Middleware。child 自己的 `system_prompt` 是追加内容，不是简单替换父提示。

限制和风险：

- 当前仍是 beta，升级版本时必须回归测试。
- child 不能再递归使用同一 `task` 路径无限 fork；框架带有递归防护。
- 继承完整对话会增加 token、缓存失效和信息暴露范围。
- fork child 不能定义自己的 `skills`，否则会和继承的 Skill 上下文产生歧义。
- 父提示中的角色和约束可能与 child 追加提示冲突。

只有 child 必须理解完整会话历史时才用 fork。可以通过一段完整 description 表达的任务，优先 isolated。

## 5. State 怎样回到父 Agent

child 完成后，框架会构造一个 `Command(update=...)`：

```text
child result
  ├─ messages：只取最终结果，转成父 task ToolMessage
  ├─ structured_response：用于生成 ToolMessage 内容，不直接覆盖父字段
  ├─ todos：不回传
  ├─ 私有字段：不回传
  └─ 其他公共字段：通过父 State reducer 合并
```

测试文件定义了公共字段 `request_id` 和 `child_note`。child 能读取父 `request_id`，在 `after_agent` 写出 `child_note`，父最终 State 能看到该字段。这说明 isolated 隔离的是对话，不等于自动丢弃所有公共业务 State。

如果多个 child 并发更新同一字段，必须为该字段设计明确 reducer；默认覆盖顺序不应被当作业务一致性策略。

## 6. Prompt、工具、权限和中断

| 能力 | 声明式 SubAgent 行为 |
| --- | --- |
| model | 使用 spec 的 `model`；应显式配置 |
| tools | 使用 spec 的 `tools`，不是自动获得所有父业务工具 |
| middleware | 使用 spec 的 middleware，并由 Deep Agents补齐必要脚手架 |
| state schema | 父 `create_deep_agent(state_schema=...)` 会转发给声明式 child |
| permissions | 默认继承父 permissions；child 自己提供时整体替换 |
| interrupt | 默认继承父 `interrupt_on`；child 自己提供时覆盖 |
| skills | isolated 可单独配置；fork 不允许单独定义 |
| backend | 使用 Deep Agents 为子 Agent 装配的文件能力；仍受实际 backend 能力限制 |

提示词不是权限。即使 child system prompt 说“不要写文件”，只要工具层允许，模型仍可能尝试写入。强制控制必须放在 permissions、HITL、工具实现或 Sandbox。

## 7. 错误、取消与持久化

- child run 是父 `task` 调用中的同步嵌套执行，默认没有独立的远程 thread。
- child 异常通常会使 `task` 失败，并影响父 run；业务上可重试的错误要有限重试，不要重试非幂等写操作。
- 父 run 被取消时，正在等待的同步 child 调用也应结束，但外部工具副作用未必能回滚。
- 父 checkpointer 保存合并后的父 State；不要假设它自动提供一个可以单独恢复的 child thread。
- child 内部需要可恢复长流程时，通常应改用自行管理持久化的 CompiledSubAgent 或远程 AsyncSubAgent。

## 8. LangSmith 中看什么

运行：

```powershell
uv run python examples/declarative_subagent.py --mode isolated
uv run python examples/declarative_subagent.py --mode fork
```

配置 `LANGSMITH_TRACING=true` 后，重点检查：

1. 父模型为什么选择 `risk-reviewer`。
2. `task.description` 是否包含完整业务上下文。
3. child run 是否带 `ls_agent_type="subagent"` metadata。
4. isolated child 的输入是否没有父对话全文。
5. fork child 的输入是否包含父有效对话。
6. child 使用了哪些工具，父 Agent 最终怎样引用 child 报告。
7. 是否出现重复委派、过度 fork 或父 child 工具职责重叠。

脚本额外写入：

```text
subagent_kind=declarative
subagent_mode=isolated|fork
entrypoint=examples/declarative_subagent.py
```

## 9. 不调用模型的测试

```powershell
uv run python examples/test_declarative_subagent.py
```

测试通过脚本化父/子 Fake Model 断言：

- isolated 只收到委托 description，不收到父对话标记。
- fork 能收到父有效对话。
- 两种模式都能传播兼容的公共 State。
- child 最终 `AIMessage` 会变成父消息流中的 `ToolMessage`。

## 10. 选择建议

使用声明式 SubAgent，当：

- child 只是一个清晰的专家角色。
- 工具集合和 prompt 可以由配置表达。
- child 与父 run 同步完成即可。
- 不需要复用已经构建好的 Graph。

改用 CompiledSubAgent，当 child 已经是独立 Agent/StateGraph，或者需要自有 schema、Middleware、HITL、checkpointer。改用 AsyncSubAgent，当任务必须在独立远程 thread 后台运行。

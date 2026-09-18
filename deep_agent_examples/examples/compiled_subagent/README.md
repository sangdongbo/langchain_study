# CompiledSubAgent：复用现成 Agent 与 StateGraph

`CompiledSubAgent` 接收一个已经构建好的 `Runnable`。Deep Agents 只负责把它挂到父 Agent 的 `task` 工具上，不会重新替它选择模型、工具、Middleware 或 State schema。

对应文件：

- 真实模型与 LangSmith：[run.py](run.py)
- 确定性测试：[test.py](test.py)

## 1. 与声明式 SubAgent 的根本区别

```text
声明式 SubAgent
  spec(model/tools/prompt/...)
  -> Deep Agents 调用 create_agent 编译

CompiledSubAgent
  应用先得到 runnable
  -> Deep Agents 原样注册 runnable
```

最小结构：

```python
finance_graph = create_agent(
    model=model,
    tools=[calculate_total, check_budget],
    system_prompt="Verify finance evidence.",
)

finance_subagent: CompiledSubAgent = {
    "name": "finance-reviewer",
    "description": "Runs a precompiled finance graph.",
    "runnable": finance_graph,
}
```

`runnable` 可以是：

- `langchain.agents.create_agent()` 的结果。
- 自定义编译后的 LangGraph `StateGraph`。
- 任何遵守输入输出契约的 LangChain `Runnable`。

## 2. 调用生命周期

```text
应用构建并编译 runnable
  -> create_deep_agent 注册 CompiledSubAgent
  -> 父模型调用 task
  -> 构造 runnable input State
  -> runnable.invoke / ainvoke
  -> 校验返回 dict 包含 messages
  -> 选择 structured_response 或 AIMessage 文本
  -> 生成父 task ToolMessage
  -> 合并兼容的公共 State
```

它仍然是同步 `task`：父 Agent 等待 runnable 返回。名字中的 Compiled 不代表后台任务，AsyncSubAgent 才是远程后台运行。

## 3. 强制输出契约

返回状态必须包含 `messages`：

```python
{
    "messages": [AIMessage(content="finance result")]
}
```

缺少该字段会抛出：

```text
CompiledSubAgent must return a state containing a 'messages' key
```

自定义 StateGraph 应使用 `MessagesState`，或者声明包含兼容 `messages` reducer 的 State schema。仅返回 `{"answer": ...}` 不符合 CompiledSubAgent 契约。

## 4. 父 Agent 最终拿到什么

返回选择顺序：

```text
structured_response 非空
  -> JSON 序列化
  -> 父 task ToolMessage.content

否则
  -> 从后向前找最后一个非空 AIMessage
  -> 文本成为父 task ToolMessage.content
```

如果末尾存在一个空的 `AIMessage`，框架会继续向前寻找非空文本。这样可兼容部分 Provider 在工具调用后生成的空结束消息。

结构化结果适合程序化合并：

```python
class Findings(TypedDict):
    decision: str
    gap: float
```

但父 Agent 收到的仍是 `task` 工具消息文本。需要父 Graph 直接消费强类型字段时，应设计公共 State 字段及 reducer，或者把编排上移到显式 StateGraph，而不是完全依赖模型解析 JSON 文本。

## 5. 不会自动继承什么

| 父能力 | CompiledSubAgent 是否自动继承 |
| --- | --- |
| model | 否；runnable 已经决定 |
| tools | 否；runnable 已经决定 |
| system prompt | 否；默认 isolated 只传任务消息 |
| user middleware | 否 |
| 父 `state_schema` | 否；runnable schema 独立 |
| `interrupt_on` | 否；必须在 runnable 内配置 |
| checkpointer | 否；必须在编译 runnable 时配置 |
| private Middleware State | 否 |
| tracing callbacks/tags | 调用配置会沿嵌套 run 传播 |

这正是 CompiledSubAgent 的价值和风险：边界清晰、容易复用，但应用必须自己把 child 构建完整。

## 6. State schema 的实际效果

父 task 会准备输入 dict，但 runnable 只会保留自己声明的 State channel。测试中父 State 有 `request_id`，child 使用 `MessagesState`；child node 实际看到的 State 中没有 `request_id`。

如果确实需要该字段：

```python
class FinanceState(MessagesState):
    request_id: NotRequired[str]
```

然后用 `StateGraph(FinanceState)` 编译 runnable。不要因为父 Agent 声明过字段，就假设不透明的 compiled runnable 自动接受它。

## 7. isolated 与 fork

CompiledSubAgent 默认也是 isolated：child messages 由 task description 重新建立，同时可传递其 schema 接受的公共 State。

设置 `mode="fork"` 后，会把父有效对话加到 child messages，但有两个重要差异：

- compiled runnable 是不透明的，框架不会替它重建父 Middleware 或修改它自己的 system prompt。
- private State 不会传入 compiled runnable；只传递允许的公共字段。

因此 Compiled fork 更像“给现成 runnable 一份父对话输入”，而不是把 runnable 改造成父 Agent 的完整克隆。

## 8. Checkpointer、HITL 和恢复

Compiled runnable 如果需要持久化，必须在它自己的编译阶段配置 checkpointer：

```python
compiled = builder.compile(checkpointer=child_checkpointer)
```

注意：

- 父 `thread_id` 是否适合作为 child checkpoint key，需要显式设计；不要无意让多个 child 共享同一命名空间。
- child 的 HITL 中断必须由 child runnable 自己配置和处理。
- 父 `interrupt_on` 不会自动保护 child 内部工具。
- child 恢复后怎样把结果交回仍在等待的父 run，是一个工作流设计问题；复杂 durable child 通常更适合显式 StateGraph 或 AsyncSubAgent。

## 9. LangSmith 中看什么

运行：

```powershell
uv run python examples/compiled_subagent/run.py
```

重点检查：

1. 父 `task` 调用选择了哪个 compiled runnable。
2. child run 的名称是否为 spec `name`。
3. child 自己的模型、工具和 Middleware 是否与父级区分清楚。
4. 返回给父 `ToolMessage` 的内容来自 structured response 还是 AI 文本。
5. 父 trace tags/metadata 是否传播到嵌套 run。

脚本写入：

```text
subagent_kind=compiled
entrypoint=examples/compiled_subagent/run.py
```

## 10. 不调用模型的测试

```powershell
uv run python examples/compiled_subagent/test.py
```

测试构造两个真实编译的 `StateGraph` 和一个错误 `RunnableLambda`，验证：

- `structured_response` 优先于 AI 文本。
- 没有结构化结果时使用最后一个非空 `AIMessage`。
- 父级未在 child schema 声明的字段不会自动继承。
- 缺少 `messages` 会产生明确错误，而不是静默返回空结果。

## 11. 选择建议

使用 CompiledSubAgent，当：

- 已经有可复用的 Agent 或 LangGraph。
- child 需要不同 State schema 或 Middleware。
- child 需要独立 response format。
- 团队希望父 Agent 只依赖稳定 runnable 契约。

简单角色分工用声明式 SubAgent 更少代码；远程后台任务用 AsyncSubAgent。

# Python 与 LangGraph 常用知识点整理

本文档用于快速复习 LangGraph 的 Agent、图编排、记忆、流式、人机协作、多智能体、部署和调试知识点。它和 `python_langchain_notes.md` 分开保存，便于把 LangChain 的组件学习和 LangGraph 的流程编排学习分开看。

整理原则：

- 以 LangGraph 中文文档的导航为主线，尽量覆盖主要主题。
- 不照搬官方原文，改写成适合学习复习的笔记。
- 示例以 Python 为主，重点理解概念、调用方式和常见模式。
- LangGraph 版本变化较快，遇到 API 差异时优先查看官方文档。

## 一、LangGraph 是什么

LangGraph 是 LangChain 生态中用于构建有状态 Agent 和复杂 LLM 工作流的框架。它不是替代 LangChain，而是把 LangChain 中的模型、工具、消息、Runnable、检索等组件组织成可控的图流程。

简单理解：

```text
LangChain 更偏组件：模型、Prompt、工具、链、检索器。
LangGraph 更偏编排：状态、节点、边、循环、暂停、恢复、多代理。
```

LangGraph 适合这些场景：

- Agent 需要多步推理和多次工具调用。
- 需要保存对话状态，支持中断后继续。
- 需要人工审批、人工修改工具参数或人工补充信息。
- 需要流式展示 Agent 正在执行哪一步。
- 需要多代理协作，例如主管代理、专家代理、交接流程。
- 需要调试、回放、时间旅行或生产部署。

如果只是一次简单模型调用或固定 RAG 链，普通 LangChain 链通常就够了；如果流程中有循环、分支、状态恢复和人工介入，LangGraph 更合适。

## 二、安装与快速创建 Agent

常用安装：

```bash
pip install -U langgraph langchain langchain-deepseek
```

如果使用 DeepSeek 的 OpenAI 兼容接口，也可以安装 OpenAI 集成：

```bash
pip install -U langgraph langchain langchain-openai
```

预构建 ReAct Agent 示例：

```python
import os

from langchain_deepseek import ChatDeepSeek
from langchain.agents import create_agent


def get_weather(city: str) -> str:
    """查询指定城市的天气。"""
    return f"{city} 今天晴。"


model = ChatDeepSeek(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0,
)

agent = create_agent(
    model=model,
    tools=[get_weather],
    system_prompt="你是一个简洁可靠的助手。",
)

response = agent.invoke(
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]}
)
```

`create_agent` 会生成一个常见的“模型判断 -> 调工具 -> 观察结果 -> 再判断 -> 最终回答”的 Agent 图。LangGraph v1 之后推荐从 `langchain.agents` 导入 `create_agent`；旧的 `langgraph.prebuilt.create_react_agent` 已经是弃用兼容入口。学习阶段可以先用 `create_agent`，理解后再写底层 `StateGraph`。

## 三、Agent 的基本组成

一个 Agent 通常由三部分组成：

| 组成 | 作用 |
| --- | --- |
| LLM | 负责理解任务、生成回复、决定是否调用工具 |
| Tools | 外部能力，例如查询天气、搜索、读文件、调用业务 API |
| Prompt | 约束 Agent 的角色、目标、边界和输出风格 |

典型循环：

```text
用户输入
-> LLM 判断是否需要工具
-> 如果需要，生成工具调用
-> 工具执行并返回观察结果
-> LLM 根据观察结果继续推理
-> 信息足够后输出最终答案
```

LangGraph 的价值是让这个循环可控、可保存、可恢复、可观察。

## 四、运行 Agent

LangGraph Agent 的输入通常是一个字典，核心字段是 `messages`。

常见输入格式：

```python
agent.invoke({"messages": "你好"})

agent.invoke({"messages": {"role": "user", "content": "你好"}})

agent.invoke(
    {"messages": [{"role": "user", "content": "你好"}]}
)
```

输出通常也是字典：

- `messages`：本次运行产生的所有消息，包括用户消息、AI 消息、工具调用消息。
- `structured_response`：如果配置了结构化输出，会包含结构化结果。
- 自定义状态字段：如果定义了自己的状态，也可能出现在输出里。

调用方式：

```python
# 同步，等待完整结果
result = agent.invoke({"messages": [{"role": "user", "content": "你好"}]})

# 异步
result = await agent.ainvoke({"messages": [{"role": "user", "content": "你好"}]})

# 同步流式
for chunk in agent.stream({"messages": [{"role": "user", "content": "你好"}]}):
    print(chunk)

# 异步流式
async for chunk in agent.astream({"messages": [{"role": "user", "content": "你好"}]}):
    print(chunk)
```

控制执行时还可以设置最大迭代次数，避免 Agent 工具调用循环停不下来。

## 五、模型配置

推荐直接创建 DeepSeek 模型对象，再传给 Agent。注意这里使用的是 `langchain.agents.create_agent`：

```python
import os

from langchain_deepseek import ChatDeepSeek

model = ChatDeepSeek(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    temperature=0,
)

agent = create_agent(
    model=model,
    tools=[get_weather],
)
```

如果当前环境没有 `langchain-deepseek`，也可以使用 DeepSeek 的 OpenAI 兼容接口：

```python
import os

from langchain_openai import ChatOpenAI
from langchain.agents import create_agent

model = ChatOpenAI(
    model="deepseek-chat",
    api_key=os.getenv("DEEPSEEK_API_KEY"),
    base_url="https://api.deepseek.com",
    temperature=0,
)

agent = create_agent(
    model=model,
    tools=[get_weather],
)
```

模型注意点：

- 工具调用 Agent 要求模型本身支持 tool calling。
- DeepSeek 常用模型名是 `deepseek-chat`；如果使用推理模型，可按当前 DeepSeek 文档替换模型名。
- 建议把密钥放在环境变量 `DEEPSEEK_API_KEY` 中，不要写死在代码里。
- `temperature=0` 更适合稳定的工具路由和教学示例。
- 可以为模型配置超时、重试、备用模型和禁用流式输出。
- 生产环境建议显式处理模型调用失败、限流和网络异常。

## 六、System Prompt

`create_agent` 使用 `system_prompt` 设置 Agent 的系统提示词。它用来约束角色、回答边界、工具使用规则和输出风格。

基础写法：

```python
agent = create_agent(
    model=model,
    tools=[get_weather],
    system_prompt="你是一个客服助手，回答要简洁。",
)
```

如果需要把用户 ID、租户、权限等运行时信息传给工具，不建议让模型自己填写这些字段，而是使用下一节的 `context_schema` 和 `ToolRuntime`。

## 七、工具

工具是一种封装函数及其输入模式的方式。模型不会直接执行代码，而是生成工具调用请求，由 LangGraph 或工具节点执行。

普通函数可以直接作为工具：

```python
def multiply(a: int, b: int) -> int:
    """计算两个整数的乘积。"""
    return a * b


agent = create_agent(
    model=model,
    tools=[multiply],
)
```

也可以使用 LangChain 的 `@tool` 获得更明确的名称、描述和参数模式：

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class MultiplyInput(BaseModel):
    a: int = Field(description="第一个整数")
    b: int = Field(description="第二个整数")


@tool("multiply_tool", args_schema=MultiplyInput)
def multiply(a: int, b: int) -> int:
    """计算两个整数的乘积。"""
    return a * b
```

工具设计重点：

- 工具名称要表达动作，例如 `search_order`、`get_weather`。
- docstring 要写清楚什么时候调用、参数含义、返回内容。
- 参数尽量简单，复杂对象用 Pydantic 描述。
- 不要把用户不能控制的参数暴露给模型，例如 `user_id`、权限、内部 token。
- 危险工具要加人工审批，例如删除、付款、发邮件、数据库写入。

工具高级能力：

- 隐藏运行时参数：从 `state` 或 `config` 中读取，而不是让模型填写。
- 禁用并行工具调用：避免多个工具同时写入外部系统。
- 直接返回工具结果：某些场景工具结果就是最终答案。
- 强制使用工具：让模型必须选择某个工具。
- 处理工具错误：返回可读错误，或让 Agent 决定是否重试。

## 八、MCP 集成

MCP 是 Model Context Protocol，用于把外部工具和上下文以统一协议提供给模型。LangGraph 可以通过 `langchain-mcp-adapters` 使用 MCP 服务器上的工具。

安装：

```bash
pip install langchain-mcp-adapters
```

示意代码：

```python
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain.agents import create_agent

client = MultiServerMCPClient(
    {
        "math": {
            "command": "python",
            "args": ["D:/path/to/math_server.py"],
            "transport": "stdio",
        }
    }
)

tools = await client.get_tools()
agent = create_agent(model=model, tools=tools)
```

MCP 适合把工具独立成服务，例如文件系统工具、业务系统工具、搜索工具、内部 API 工具。这样 Agent 不需要关心工具运行在哪，只要拿到工具描述和调用协议即可。

## 九、Context 上下文

LangGraph 中的上下文不只是聊天消息。它可以是用户身份、权限、API 密钥、业务配置、工具中间结果、长期记忆等。

常见上下文类型：

| 类型 | 是否可变 | 生命周期 | 适合内容 |
| --- | --- | --- | --- |
| `config` | 不可变 | 单次运行 | `user_id`、租户、权限、API 凭据 |
| `state` | 可变 | 单次运行或线程 | 中间结果、消息、步骤状态 |
| `store` | 可变 | 跨线程 | 用户偏好、长期资料、历史事实 |

运行时配置示例：

```python
agent.invoke(
    {"messages": [{"role": "user", "content": "帮我查订单"}]},
    config={"configurable": {"user_id": "user-123"}},
)
```

配置适合传不可变运行参数；如果要让工具读取强类型上下文，推荐使用 `context_schema`。

工具读取 context 示例：

```python
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool


@dataclass
class Context:
    user_id: str


@tool
def get_user_profile(runtime: ToolRuntime[Context]) -> str:
    """读取当前登录用户资料。"""

    user_id = runtime.context.user_id
    return f"当前用户 ID 是 {user_id}"


agent = create_agent(
    model=model,
    tools=[get_user_profile],
    context_schema=Context,
    system_prompt="你是一个可以读取运行时上下文的助手。",
)

agent.invoke(
    {"messages": [{"role": "user", "content": "查询当前用户资料"}]},
    context=Context(user_id="U001"),
)
```

仓库里的完整小例子见 `langGraph/TestContext.py`。

经验：固定不变的运行配置可以放 `config`，工具需要读取的强类型运行时信息放 `context`，执行过程中会变化的数据放 `state`，跨会话保存的数据放长期 `store`。

## 十、记忆：短期记忆与长期记忆

LangGraph 里常见两类记忆：

- 短期记忆：线程级记忆，通常是同一个对话里的消息历史和状态。
- 长期记忆：跨线程记忆，例如用户偏好、用户画像、长期任务资料。

短期记忆需要 `checkpointer` 和 `thread_id`：

```python
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent

checkpointer = InMemorySaver()

agent = create_agent(
    model=model,
    tools=[get_weather],
    checkpointer=checkpointer,
)

config = {"configurable": {"thread_id": "thread-1"}}

agent.invoke(
    {"messages": [{"role": "user", "content": "我叫小明"}]},
    config=config,
)

agent.invoke(
    {"messages": [{"role": "user", "content": "我叫什么？"}]},
    config=config,
)
```

`thread_id` 相同，就会接上同一个对话线程。`InMemorySaver` 只适合学习和本地演示，生产环境要换成数据库或平台提供的持久化存储。

长对话处理建议：

- 删除过旧或无关消息，避免上下文过长。
- 总结历史对话，把长历史压缩成短摘要。
- 重要事实写入长期记忆，例如用户偏好和稳定资料。
- 不要把所有历史都塞给模型，成本高且容易干扰回答。

## 十一、结构化输出

结构化输出用于让最终答案符合固定字段。

```python
from pydantic import BaseModel


class WeatherAnswer(BaseModel):
    city: str
    weather: str
    advice: str


agent = create_agent(
    model=model,
    tools=[get_weather],
    response_format=WeatherAnswer,
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]}
)

print(result["structured_response"])
```

适合场景：

- 信息抽取。
- 表单填充。
- 分类标签。
- API 返回固定 JSON。
- 前端需要稳定字段渲染。

## 十二、流式传输

LangGraph 支持多种流式模式。

| `stream_mode` | 作用 |
| --- | --- |
| `updates` | 每个节点执行后返回一次状态更新，适合展示 Agent 进度 |
| `messages` | 流式输出 LLM token，适合打字机效果 |
| `custom` | 工具或节点主动推送自定义进度 |
| 多模式列表 | 同时接收多类事件 |

Agent 进度流：

```python
for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]},
    stream_mode="updates",
):
    print(chunk)
```

LLM token 流：

```python
for token, metadata in agent.stream(
    {"messages": [{"role": "user", "content": "写一句问候语"}]},
    stream_mode="messages",
):
    print(token, metadata)
```

常见进度顺序：

```text
LLM 节点生成工具调用请求
-> 工具节点执行工具
-> LLM 节点根据工具结果生成最终回答
```

## 十三、人机协作与人工参与循环

人工参与循环适合在自动化流程中插入人类审批、修改和补充信息。

典型用例：

- 工具执行前人工审批，例如发邮件、付款、删除数据。
- 人工修改工具参数，例如把模型生成的收件人或金额改正确。
- 人工验证模型输出，例如合同摘要、工单处理意见。
- Agent 主动请求用户补充信息。

核心概念：

- `interrupt()`：在某个节点暂停执行，把待审信息交给人。
- `Command(resume=...)`：收到人工输入后恢复执行。
- 持久化检查点：让暂停可以跨很长时间，不依赖当前进程一直活着。

示意代码：

```python
from langgraph.types import Command, interrupt


def approval_node(state):
    review = interrupt(
        {
            "question": "是否允许发送邮件？",
            "draft": state["email_draft"],
        }
    )
    return {"approved": review["approved"]}


graph.invoke(Command(resume={"approved": True}), config=config)
```

涉及高风险动作时，人工审批比单纯依赖 Prompt 更可靠。

## 十四、多智能体

当一个 Agent 工具太多、上下文太复杂或任务领域差异很大时，可以拆成多个专业 Agent。

常见架构：

| 架构 | 含义 | 适合场景 |
| --- | --- | --- |
| 网络 | 每个 Agent 可以和其他 Agent 通信 | 灵活探索，但控制较难 |
| 主管 | 主管 Agent 决定调用哪个专家 Agent | 常见、易理解 |
| 主管工具调用 | 把专家 Agent 包装成工具给主管调用 | 工具调用模型表现好时很方便 |
| 分层 | 主管下面还有主管 | 大型复杂组织流程 |
| 自定义工作流 | 开发者明确限制哪些 Agent 能互相跳转 | 业务流程强约束 |

交接可以用 `Command` 表示：

```python
from typing import Literal
from langgraph.types import Command


def router_agent(state) -> Command[Literal["research_agent", "math_agent", "__end__"]]:
    next_agent = decide_next_agent(state)
    return Command(
        goto=next_agent,
        update={"last_router": "router_agent"},
    )
```

拆多 Agent 的原则：

- 每个 Agent 专注一个领域。
- 每个 Agent 的输入输出要清晰。
- 不要为了炫技拆太多，拆分会增加调试成本。
- 重要流程最好让主管或图边显式控制，而不是完全交给模型自由跳转。

## 十五、底层 Graph API：State、Node、Edge

LangGraph 的核心是图。

```text
State：当前状态快照。
Node：处理状态的函数。
Edge：决定下一个节点。
```

最小图示例：

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    question: str
    answer: str


def answer_node(state: State):
    return {"answer": f"你问的是：{state['question']}"}


builder = StateGraph(State)
builder.add_node("answer", answer_node)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)

graph = builder.compile()

result = graph.invoke({"question": "什么是 LangGraph？"})
```

重要理解：

- 节点和边本质上都是 Python 逻辑。
- 节点可以调用 LLM，也可以只是普通函数。
- 图必须 `.compile()` 后才能运行。
- 编译时可以加检查点、断点等运行时能力。
- `START` 是入口，`END` 是结束。

## 十六、State 与 reducer

状态是所有节点共享的数据结构。节点一般不直接修改原对象，而是返回“状态更新”。

普通字段默认会被新值覆盖；列表、消息等字段常需要 reducer 控制如何合并。

消息状态常见写法：

```python
from typing import Annotated
from typing_extensions import TypedDict
from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages


class ChatState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
```

`add_messages` 表示新消息会追加到已有消息列表，而不是覆盖整个列表。

经验：

- 状态字段不要无限膨胀。
- 对消息列表使用合适的 reducer。
- 对业务字段保持结构清楚，例如 `user_id`、`draft`、`approved`。
- 节点返回值必须符合状态更新格式，返回普通字符串容易报错。

## 十七、条件边、Send 与 Command

固定边适合线性流程：

```python
builder.add_edge("node_a", "node_b")
```

条件边适合分支：

```python
def route(state):
    if state["need_tool"]:
        return "tool_node"
    return "final_node"


builder.add_conditional_edges("model_node", route)
```

`Send` 适合动态并行分发，例如把一批文档分别交给多个节点处理。`Command` 适合把“更新状态”和“跳转节点”合在一起，常用于多代理交接、人工恢复和复杂控制流。

简化理解：

```text
add_edge：固定下一步。
add_conditional_edges：根据状态判断下一步。
Send：动态创建多个分支任务。
Command：一边更新状态，一边决定跳到哪里。
```

## 十八、持久化、线程与检查点

LangGraph 的持久化通过 checkpointer 实现。它会在图的每个关键步骤保存状态快照。

核心概念：

- `thread`：一组相关运行，通常对应一个对话。
- `thread_id`：线程 ID，用于找到同一个会话。
- `checkpoint`：某一步的状态快照。
- `StateSnapshot`：检查点对象，包含状态值、下一步节点、任务和元数据。

最小示例：

```python
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()
graph = builder.compile(checkpointer=checkpointer)

config = {"configurable": {"thread_id": "demo-thread"}}
graph.invoke({"question": "你好"}, config=config)
```

持久化带来的能力：

- 多轮短期记忆。
- 人工参与循环。
- 失败后从检查点恢复。
- 查看历史状态。
- 时间旅行和分支调试。

## 十九、时间旅行

时间旅行指从之前的检查点恢复执行。它适合调试非确定性的 Agent，因为同一个问题可能因为模型输出不同走出不同路径。

用途：

- 回看 Agent 为什么调用某个工具。
- 从失败前的状态继续执行。
- 修改旧状态，尝试另一条路线。
- 比较不同 Prompt 或工具结果对流程的影响。

注意：从旧检查点恢复通常会形成新的执行分支，而不是覆盖原历史。

## 二十、子图

子图就是把一个图当成另一个图的节点。

适合场景：

- 多代理系统里，每个代理本身都是一个图。
- 多个工作流复用同一组节点。
- 不同团队分别维护不同子流程。
- 父图只关心子图输入输出，不关心内部细节。

两种通信方式：

- 父图和子图有共享状态字段：可以直接把子图作为节点添加。
- 父图和子图状态结构不同：在父图节点里手动调用子图，并做输入输出转换。

简单原则：共享状态越少，边界越清晰；但共享太少也会增加转换代码。

## 二十一、函数式 API

除了 `StateGraph`，LangGraph 也提供函数式 API。它更像写普通 Python 函数，但底层仍然能获得持久化、任务、恢复等能力。

常见概念：

- `entrypoint`：定义可运行入口。
- `task`：定义可被持久化和重试的任务。
- 确定性：恢复执行时，已经完成的任务可以复用结果，减少重复副作用。

适合场景：

- 流程更像普通函数调用，不想显式画图。
- 需要持久化和恢复，但工作流结构不复杂。
- 希望逐步从普通 Python 工作流迁移到 LangGraph。

学习顺序建议先掌握 `StateGraph`，再看函数式 API。

## 二十二、评估

Agent 评估用于判断 Agent 的行为是否可靠，而不只是看“最终答案像不像”。

可以评估：

- 是否调用了正确工具。
- 工具参数是否正确。
- 是否遵守系统提示词。
- 是否在信息不足时拒绝编造。
- 多步任务是否走了合理路径。
- 人工审批场景是否真的暂停。

评估器通常接收输入、输出和轨迹信息，然后返回分数或判断结果。生产项目建议为关键 Agent 写小规模评估集，尤其是工具路由和高风险流程。

## 二十三、部署与 LangGraph Platform

LangGraph 可以本地运行，也可以通过 LangGraph Platform 部署。平台相关能力包括：

- 本地 LangGraph Server。
- LangGraph Studio 可视化调试。
- 线程、运行、助手等管理。
- Webhook、Cron Job、后台运行。
- 云部署或自托管部署。

典型应用结构会包含图定义文件和配置文件，服务启动后可以通过 SDK 或 HTTP API 调用图。学习阶段优先在本地 Python 中直接调用；需要前端、多人调试或生产服务时，再考虑平台部署。

## 二十四、UI 与生成式 UI

LangGraph 的 UI 相关文档主要关注如何把 Agent 运行过程接到前端。

常见 UI 能力：

- 展示多轮对话。
- 展示 Agent 当前执行进度。
- 展示工具调用和工具结果。
- 加入人工审批入口。
- 通过生成式 UI 让 Agent 推送前端组件。

前端接入时重点关注：

- 用流式事件展示“正在思考、正在调用工具、工具完成”。
- 对高风险工具调用弹出确认界面。
- 把 `thread_id` 和用户会话绑定。
- 不要把内部状态、密钥或系统提示词直接展示给用户。

## 二十五、常见错误与排查

| 问题 | 常见原因 | 处理 |
| --- | --- | --- |
| Agent 不记得前文 | 没有 checkpointer 或 `thread_id` 变了 | 检查 `configurable.thread_id` |
| 工具不调用 | 模型不支持工具调用，或工具描述不清楚 | 换支持工具调用的模型，改清工具说明 |
| 工具参数乱填 | 参数 schema 太模糊 | 使用 Pydantic、字段描述和更明确 Prompt |
| 图运行报返回值错误 | 节点返回不符合状态更新格式 | 节点返回 dict，例如 `{"answer": "..."}` |
| 消息列表被覆盖 | 没有 reducer | 使用 `Annotated[..., add_messages]` |
| 流式没有 token | 模型或配置禁用了流式 | 检查模型能力和 `disable_streaming` |
| 人工暂停后无法恢复 | 没有持久化或配置不一致 | 使用 checkpointer，并保持同一 `thread_id` |
| Agent 死循环 | 停止条件不清楚或工具结果无效 | 设置最大迭代次数，改路由和 Prompt |

## 二十六、学习路线与小抄

建议顺序：

1. 先会用 `create_agent` 创建工具调用 Agent。
2. 掌握 `invoke`、`stream`、`messages` 输入输出。
3. 学会配置模型、Prompt、工具和结构化输出。
4. 加入 checkpointer 和 `thread_id`，理解短期记忆。
5. 学习 `StateGraph`、`State`、`Node`、`Edge`。
6. 学习条件边、reducer、`Command`。
7. 学习人工参与循环和时间旅行。
8. 学习多代理、子图和部署。

常用小抄：

```python
# 预构建 Agent
agent = create_agent(
    model=model,
    tools=[get_weather],
    checkpointer=checkpointer,
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]},
    config={"configurable": {"thread_id": "thread-1"}},
)

# 工具读取运行时 context
agent.invoke(
    {"messages": [{"role": "user", "content": "查询当前用户资料"}]},
    context=Context(user_id="U001"),
)

# 最小状态图
builder = StateGraph(State)
builder.add_node("answer", answer_node)
builder.add_edge(START, "answer")
builder.add_edge("answer", END)
graph = builder.compile()
```

本阶段小结：

- LangGraph 用图来编排 Agent，核心是状态、节点和边。
- 预构建 `create_agent` 适合快速上手。
- `messages` 是 Agent 最常见的输入输出核心字段。
- `checkpointer + thread_id` 是短期记忆和恢复能力的关键。
- 流式模式可以展示 Agent 进度、模型 token 和工具进度。
- 人工参与循环适合高风险工具和需要审批的业务流程。
- 多代理适合拆分复杂职责，但会增加系统复杂度。
- 生产环境要重视工具安全、持久化、评估和可观测性。

## 二十七、官方参考

LangGraph 版本迭代较快，遇到 API 差异时优先查看官方文档：

- LangGraph 快速入门: <https://langgraph.com.cn/agents/agents.1.html>
- LangGraph 代理概述: <https://langgraph.com.cn/agents/overview.1.html>
- LangGraph 运行代理: <https://langgraph.com.cn/agents/run_agents.1.html>
- LangGraph 流式传输: <https://langgraph.com.cn/agents/streaming/index.html>
- LangGraph 模型: <https://langgraph.com.cn/agents/models/index.html>
- LangGraph 工具: <https://langgraph.com.cn/agents/tools.1.html>
- LangGraph MCP 集成: <https://langgraph.com.cn/agents/mcp/index.html>
- LangGraph 上下文: <https://langgraph.com.cn/agents/context/index.html>
- LangGraph 内存: <https://langgraph.com.cn/agents/memory/index.html>
- LangGraph 人机协作: <https://langgraph.com.cn/agents/human-in-the-loop/index.html>
- LangGraph 多智能体: <https://langgraph.com.cn/agents/multi-agent.1.html>
- LangGraph 评估: <https://langgraph.com.cn/agents/evals/index.html>
- LangGraph 部署: <https://langgraph.com.cn/agents/deployment/index.html>
- LangGraph UI: <https://langgraph.com.cn/agents/ui/index.html>
- LangGraph 图 API 概念: <https://langgraph.com.cn/concepts/low_level.1.html>
- LangGraph 持久化: <https://langgraph.com.cn/concepts/persistence.1.html>
- LangGraph 流式传输概念: <https://langgraph.com.cn/concepts/streaming.1.html>
- LangGraph 记忆概念: <https://langgraph.com.cn/concepts/memory.1.html>
- LangGraph 人工参与循环: <https://langgraph.com.cn/concepts/human_in_the_loop.1.html>
- LangGraph 多代理系统: <https://langgraph.com.cn/concepts/multi_agent.1.html>
- LangGraph 子图: <https://langgraph.com.cn/concepts/subgraphs.1.html>
- LangGraph 时间旅行: <https://langgraph.com.cn/concepts/time-travel/index.html>
- LangGraph 工具概念: <https://langgraph.com.cn/concepts/tools/index.html>
- LangGraph 函数式 API: <https://langgraph.com.cn/concepts/functional_api.1.html>


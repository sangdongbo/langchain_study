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

更细一点说：

| 框架 | 主要定位 | 典型能力 |
| --- | --- | --- |
| LangChain | 提供集成组件和可组合组件，简化 LLM 应用开发 | 模型接入、Prompt、工具、链、检索、输出解析 |
| LangGraph | 在 LangChain 组件之上做智能体编排和工作流创建 | 持久化、流式输出、AgentOps、Memory、Human-in-loop、LangGraph Platform、LangGraph Studio |

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
pip install -U langgraph langchain langchain-openai python-dotenv
```

如果还要直接使用 DeepSeek 官方封装，可以额外安装：

```bash
pip install -U langchain-deepseek
```

预构建 ReAct Agent 示例：

```python
import os

# create_agent 会帮我们创建一个预构建的工具调用 Agent。
from langchain.agents import create_agent
from langchain_openai import ChatOpenAI


def get_weather(city: str) -> str:
    """查询指定城市的天气。

    这个 docstring 很重要，模型会根据它判断什么时候调用这个工具。
    """
    return f"{city} 今天晴。"


model = ChatOpenAI(
    # 阿里云百炼、DeepSeek、本地 vLLM/SGLang 等 OpenAI 兼容接口都可以这样接。
    model=os.getenv("OPENAI_MODEL", "qwen-plus"),
    api_key=os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY"),
    base_url=os.getenv(
        "OPENAI_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    # 设为 0 可以让输出更稳定，方便学习和调试。
    temperature=0,
)

agent = create_agent(
    # Agent 背后使用的模型。
    model=model,
    # 传入工具列表，模型需要时会生成工具调用请求。
    tools=[get_weather],
    # 系统提示词用于约束 Agent 的角色和回答风格。
    system_prompt="你是一个简洁可靠的助手。",
)

response = agent.invoke(
    # messages 是 Agent 最常见的输入字段。
    # 这里传入一条 user 消息，Agent 会根据内容决定是否调用 get_weather。
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]}
)
```

这段代码可以按步骤理解：

1. `get_weather(city: str)`：定义一个普通 Python 函数，它会被包装成 Agent 可调用的工具。
2. `ChatOpenAI(...)`：创建 OpenAI 兼容模型对象。百炼、DeepSeek 兼容接口、本地 OpenAI 兼容服务都可以通过 `base_url` 接入。
3. `create_agent(...)`：把模型、工具和系统提示词组装成一个可运行 Agent。
4. `agent.invoke(...)`：同步运行 Agent，并传入用户消息。
5. 返回的 `response` 通常是一个字典，其中最重要的是 `messages`，里面会记录用户消息、AI 消息、工具调用和工具结果。

`create_agent` 会生成一个常见的“模型判断 -> 调工具 -> 观察结果 -> 再判断 -> 最终回答”的 Agent 图。LangGraph v1 之后推荐从 `langchain.agents` 导入 `create_agent`；旧的 `langgraph.prebuilt.create_react_agent` 属于迁移期兼容入口，旧课件里看到时直接换成 `create_agent`。学习阶段可以先用 `create_agent`，理解后再写底层 `StateGraph`。

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

### Workflows 和 Agent 的区别

Workflows 更像“开发者提前写好流程，LLM 在流程中的某些步骤工作”。Agent 更像“LLM 根据环境反馈，自己决定下一步行动”。

| 类型 | 控制方式 | 常见模式 |
| --- | --- | --- |
| Workflows | LLM 被嵌入到预定义代码路径中，由代码引导控制流 | Prompt Chaining、Parallelization、Orchestrator-Worker、Evaluator-Optimizer、Routing |
| Agent | LLM 根据工具返回、环境反馈和任务状态不断决定下一步 | LLM call -> Tool action -> feedback loop -> Out |

Workflows 的优点是更稳定、更容易预测；Agent 的优点是更加灵活、更加智能，适合开放式任务。实际项目里经常会混合使用：外层用 LangGraph 控制关键路径，局部步骤交给 Agent 自主决策。

## 四、运行 Agent

LangGraph Agent 的输入通常是一个字典，核心字段是 `messages`。

常见输入格式：

```python
# 最简写法：直接把字符串作为 messages 传入。
agent.invoke({"messages": "你好"})

# 单条消息写法：明确 role 和 content。
agent.invoke({"messages": {"role": "user", "content": "你好"}})

# 多条消息写法：最常见，也最推荐，方便保存完整对话历史。
agent.invoke(
    {"messages": [{"role": "user", "content": "你好"}]}
)
```

这三种写法本质上都是告诉 Agent：“当前用户输入是什么”。实际项目里更推荐第三种列表形式，因为后续可以自然追加多轮消息、工具消息和系统消息。

输出通常也是字典：

- `messages`：本次运行产生的所有消息，包括用户消息、AI 消息、工具调用消息。
- `structured_response`：如果配置了结构化输出，会包含结构化结果。
- 自定义状态字段：如果定义了自己的状态，也可能出现在输出里。

调用方式：

```python
# 同步，等待完整结果
result = agent.invoke({"messages": [{"role": "user", "content": "你好"}]})

# 异步，适合放在 FastAPI、异步 Web 服务或异步任务中
result = await agent.ainvoke({"messages": [{"role": "user", "content": "你好"}]})

# 同步流式，每产生一个事件或状态片段就 yield 一次
for chunk in agent.stream({"messages": [{"role": "user", "content": "你好"}]}):
    print(chunk)

# 异步流式，适合 WebSocket、SSE 等实时输出场景
async for chunk in agent.astream({"messages": [{"role": "user", "content": "你好"}]}):
    print(chunk)
```

这段代码可以按步骤理解：

1. `invoke`：最简单，调用后一直等到 Agent 完整运行结束。
2. `ainvoke`：异步版本，不阻塞事件循环。
3. `stream`：同步流式输出，适合在命令行或普通脚本里观察 Agent 每一步。
4. `astream`：异步流式输出，适合前端实时展示。
5. `chunk`：不是固定一种格式，它会受 `stream_mode` 影响，可能是状态更新、消息 token 或自定义事件。

控制执行时还可以设置最大迭代次数，避免 Agent 工具调用循环停不下来。

## 五、模型配置

推荐先创建模型对象，再传给 `langchain.agents.create_agent`。现在很多服务都提供 OpenAI 兼容接口，例如阿里云百炼、DeepSeek 兼容接口、本地 vLLM、本地 SGLang 等，所以学习文档里优先使用 `langchain_openai.ChatOpenAI` 作为统一写法。

```python
import os

from langchain.agents import create_agent
from langchain_openai import ChatOpenAI

model = ChatOpenAI(
    # 阿里云百炼示例。也可以在 .env 里改成 qwen-max、qwen-plus 等。
    model=os.getenv("OPENAI_MODEL", "qwen-plus"),
    # 百炼建议读取 DASHSCOPE_API_KEY；其他兼容服务也可以用 OPENAI_API_KEY。
    api_key=os.getenv("DASHSCOPE_API_KEY") or os.getenv("OPENAI_API_KEY"),
    # 百炼 OpenAI 兼容模式地址。DeepSeek 或本地服务时改这个 base_url 即可。
    base_url=os.getenv(
        "OPENAI_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    ),
    # 低随机性更适合工具调用和文档示例。
    temperature=0,
)

agent = create_agent(
    # 这里直接传模型对象，不需要再写 provider 字符串。
    model=model,
    # 工具列表可以为空，也可以放多个工具函数。
    tools=[get_weather],
)
```

如果项目确实要使用 DeepSeek 官方封装，也可以保留 `langchain-deepseek`：

```python
import os

from langchain.agents import create_agent
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

模型注意点：

- 工具调用 Agent 要求模型本身支持 tool calling。
- 阿里云百炼 OpenAI 兼容地址通常是 `https://dashscope.aliyuncs.com/compatible-mode/v1`。
- DeepSeek 常用模型名是 `deepseek-chat`；百炼常用模型可以按 `.env` 的 `OPENAI_MODEL` 配置。
- 本地私有化模型也可以接 `ChatOpenAI`，只要服务暴露 OpenAI 兼容接口，例如 `http://localhost:8000/v1`。
- 本地模型工具调用容易受服务端解析器影响。vLLM/SGLang 等需要确认模型和 tool-call parser 匹配，例如 Qwen 系模型使用对应 Qwen parser，Hermes 系模型使用 Hermes parser。
- 建议把密钥放在环境变量中，例如 `DASHSCOPE_API_KEY`、`DEEPSEEK_API_KEY`、`OPENAI_API_KEY`，不要写死在代码里。
- `temperature=0` 更适合稳定的工具路由和教学示例。
- 可以为模型配置超时、重试、备用模型和禁用流式输出。
- 生产环境建议显式处理模型调用失败、限流和网络异常。
- 如果本地模型开启 thinking/reasoning 模板，需要确认返回格式仍然兼容工具调用；工具调用失败时先关闭流式和 thinking，再排查模型输出。

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
    """计算两个整数的乘积。

    函数说明会暴露给模型，所以要写清楚工具能做什么。
    """
    return a * b


agent = create_agent(
    model=model,
    # 普通函数可以直接放进 tools，LangChain 会自动推断名称和参数。
    tools=[multiply],
)
```

这段代码可以按步骤理解：

1. `multiply(a: int, b: int)`：类型注解会帮助工具生成参数 schema。
2. docstring：会成为工具描述的一部分，影响模型是否能正确选择工具。
3. `tools=[multiply]`：把函数注册给 Agent，之后模型可以请求调用它。
4. 工具真正执行时，不是模型直接跑 Python，而是 Agent 框架收到模型的工具调用请求后再执行函数。

也可以使用 LangChain 的 `@tool` 获得更明确的名称、描述和参数模式：

```python
from langchain_core.tools import tool
from pydantic import BaseModel, Field


class MultiplyInput(BaseModel):
    # Field 的 description 会进入工具参数说明，帮助模型填对参数。
    a: int = Field(description="第一个整数")
    b: int = Field(description="第二个整数")


@tool("multiply_tool", args_schema=MultiplyInput)
def multiply(a: int, b: int) -> int:
    """计算两个整数的乘积。"""
    return a * b
```

这段代码可以按步骤理解：

1. `MultiplyInput(BaseModel)`：用 Pydantic 明确工具的入参结构。
2. `Field(description=...)`：告诉模型每个参数是什么意思，减少参数填错。
3. `@tool("multiply_tool", args_schema=MultiplyInput)`：指定工具名和参数 schema。
4. 工具名建议用动词或动词短语，例如 `multiply_tool`、`search_order`、`get_weather`。
5. 如果工具参数比较复杂，优先用 Pydantic，而不是只靠函数签名。

工具设计重点：

- 工具名称要表达动作，例如 `search_order`、`get_weather`。
- docstring 要写清楚什么时候调用、参数含义、返回内容。
- 参数尽量简单，复杂对象用 Pydantic 描述。
- 不要把用户不能控制的参数暴露给模型，例如 `user_id`、权限、内部 token。
- 危险工具要加人工审批，例如删除、付款、发邮件、数据库写入。

工具高级能力：

- 隐藏运行时参数：从 `ToolRuntime.context`、`ToolRuntime.state` 或后端会话中读取，而不是让模型填写。
- 禁用并行工具调用：避免多个工具同时写入外部系统。
- 直接返回工具结果：某些场景工具结果就是最终答案。
- 强制使用工具：让模型必须选择某个工具。
- 处理工具错误：返回可读错误，或让 Agent 决定是否重试。

如果你已经写好了 LCEL 链，也可以把 `Runnable` 转成工具。截图里的 `prompt | llm | StrOutputParser()` 就适合这种场景：

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from pydantic import BaseModel, Field


class SummaryArgs(BaseModel):
    topic: str = Field(description="需要总结的主题")
    language: str = Field(default="zh", description="输出语言，例如 zh 或 en")


prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "你是一个文档总结助手。"),
        ("user", "请用 {language} 总结这个主题：{topic}"),
    ]
)

summary_chain = prompt | model | StrOutputParser()

summary_tool = summary_chain.as_tool(
    name="summarize_topic",
    description="按指定语言总结一个主题。",
    args_schema=SummaryArgs,
)
```

如果工具需要复杂初始化、复用第三方客户端或自定义同步/异步执行，可以继承 `BaseTool`。新版 Pydantic/LangChain 对类字段注解更严格，`name`、`description`、`args_schema` 这些字段建议显式写类型：

```python
from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class SearchArgs(BaseModel):
    query: str = Field(description="搜索关键词")


class WebSearchTool(BaseTool):
    name: str = "web_search"
    description: str = "搜索互联网并返回简短结果。"
    args_schema: Type[BaseModel] = SearchArgs
    return_direct: bool = False

    def _run(self, query: str) -> str:
        # 这里可以调用你自己的搜索客户端，例如 Tavily、百炼联网搜索或企业搜索 API。
        return f"搜索结果：{query}"
```

一般优先级是：简单工具用普通函数或 `@tool`；已有链路复用用 `Runnable.as_tool(...)`；需要封装客户端、鉴权、同步/异步细节时再继承 `BaseTool`。

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
        # math 是这个 MCP 服务的本地名称，可以按业务取名。
        "math": {
            # 通过 stdio 启动一个本地 Python MCP Server。
            "command": "python",
            "args": ["D:/path/to/math_server.py"],
            "transport": "stdio",
        }
    }
)

# 从 MCP Server 拉取工具描述和调用方式。
tools = await client.get_tools()

# MCP 工具拿到后，和普通 tools 一样传给 Agent。
agent = create_agent(model=model, tools=tools)
```

这段代码可以按步骤理解：

1. `MultiServerMCPClient(...)`：声明要连接哪些 MCP 服务。
2. `"command"` 和 `"args"`：告诉客户端如何启动本地 MCP Server。
3. `"transport": "stdio"`：表示通过标准输入输出和 MCP Server 通信。
4. `await client.get_tools()`：异步读取服务端暴露的工具。
5. `create_agent(..., tools=tools)`：把外部服务里的工具接入 Agent。

MCP 适合把工具独立成服务，例如文件系统工具、业务系统工具、搜索工具、内部 API 工具。这样 Agent 不需要关心工具运行在哪，只要拿到工具描述和调用协议即可。

## 九、Context 上下文

LangGraph 中的上下文不只是聊天消息。它可以是用户身份、权限、API 密钥、业务配置、工具中间结果、长期记忆等。

常见上下文类型：

| 类型 | 是否可变 | 生命周期 | 适合内容 |
| --- | --- | --- | --- |
| `context` | 不可变 | 单次运行 | `user_id`、租户、权限、API 凭据、语言偏好 |
| `state` | 可变 | 单次运行或线程 | 中间结果、消息、步骤状态 |
| `store` | 可变 | 跨线程 | 用户偏好、长期资料、历史事实 |
| `config.configurable` | 不可变 | 单次运行 | `thread_id`、`checkpoint_ns`、`checkpoint_id` 等执行/检查点配置 |

旧课件里常见把 `user_id` 放进 `config={"configurable": {"user_id": "..."}}`，现在更建议区分清楚：

- 业务上下文，例如用户、租户、权限、内部 token：放 `context_schema` / `context`，工具用 `ToolRuntime.context` 读取。
- 图执行配置，例如短期记忆所需的 `thread_id`：放 `config.configurable`。
- 执行过程中会被节点或工具更新的数据：放 `state`。
- 跨线程长期记忆：放 `store`。

工具读取 context 示例：

```python
from dataclasses import dataclass

from langchain.agents import create_agent
from langchain.tools import ToolRuntime, tool


@dataclass
class Context:
    # 这里定义工具可以读取的运行时上下文字段。
    user_id: str


@tool
def get_user_profile(runtime: ToolRuntime[Context]) -> str:
    """读取当前登录用户资料。"""

    # runtime.context 来自 agent.invoke(..., context=Context(...))。
    # 这样 user_id 不需要让模型猜，也不会作为普通工具参数暴露出来。
    user_id = runtime.context.user_id
    return f"当前用户 ID 是 {user_id}"


agent = create_agent(
    model=model,
    tools=[get_user_profile],
    # 声明 context 的类型，LangGraph 才知道 runtime.context 的结构。
    context_schema=Context,
    system_prompt="你是一个可以读取运行时上下文的助手。",
)

agent.invoke(
    {"messages": [{"role": "user", "content": "查询当前用户资料"}]},
    # 真正运行时把当前用户身份传进来。
    context=Context(user_id="U001"),
    # 如果启用了 checkpointer，thread_id 仍然放在 config.configurable。
    config={"configurable": {"thread_id": "chat-U001-001"}},
)
```

这段代码可以按步骤理解：

1. `Context`：定义运行时上下文结构，例如当前用户、租户、权限等。
2. `ToolRuntime[Context]`：让工具函数可以读取运行时上下文。
3. `runtime.context.user_id`：从后端安全传入，不需要模型生成。
4. `context_schema=Context`：告诉 Agent 这个上下文长什么样。
5. `context=Context(user_id="U001")`：调用 Agent 时传入真实上下文。
6. `configurable.thread_id`：只负责告诉 checkpointer 当前是哪条会话线程。

这类写法特别适合用户 ID、权限、内部 token 这类“不能让模型自己填”的参数。

仓库里的完整小例子见 `langGraph/TestContext.py`。

工具还可以通过 `ToolRuntime` 读取状态、长期存储和工具调用 ID。工具需要更新 Agent 状态时，返回 `Command(update=...)`，不要只返回普通字符串：

```python
from dataclasses import dataclass

from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command


@dataclass
class Context:
    user_name: str


@tool
def remember_user_name(runtime: ToolRuntime[Context]) -> Command:
    """把当前用户姓名写入 Agent 状态。"""

    user_name = runtime.context.user_name
    return Command(
        update={
            "username": user_name,
            # 更新 messages 时要补 ToolMessage，否则模型可能看不到工具执行结果。
            "messages": [
                ToolMessage(
                    content=f"已读取当前用户姓名：{user_name}",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )
```

截图里出现的 `InjectedToolCallId`、`InjectedState`、`InjectedStore`、`RunnableConfig` 读取业务参数等写法，属于旧版本或迁移期写法。新文档里优先用 `ToolRuntime`，它把 `context`、`state`、`store`、`tool_call_id` 统一放在一个运行时对象里。

经验：工具需要读取的强类型运行时信息放 `context`，执行过程中会变化的数据放 `state`，跨会话保存的数据放长期 `store`，检查点和线程定位放 `config.configurable.thread_id`。

## 十、记忆：短期记忆与长期记忆

LangGraph 里常见两类记忆：

- 短期记忆：线程级记忆，通常是同一个对话里的消息历史和状态。
- 长期记忆：跨线程记忆，例如用户偏好、用户画像、长期任务资料。

可以把记忆理解成两层：

| 类型 | 作用 | 典型范围 |
| --- | --- | --- |
| 检查点记忆 | 保存和恢复图执行状态，让同一个会话能接着上次继续 | 通常 scoped to `thread_id` |
| 长期记忆 | 保存用户偏好、稳定事实、用户画像等跨会话信息 | 通常 scoped to `user_id` |

图片里的聊天例子可以这样理解：第一次会话中，应用把用户说过的重要信息写入 memory store，并绑定到 `user_id`；第二次会话即使是新的聊天线程，也可以根据同一个 `user_id` 从 memory store 读回之前保存的信息。因此 LangGraph 的“记忆”不只是把聊天消息塞回 prompt，还包括通过持久化层保存可恢复的状态和可复用的长期资料。

短期记忆需要 `checkpointer` 和 `thread_id`：

```python
from langgraph.checkpoint.memory import InMemorySaver
from langchain.agents import create_agent

# InMemorySaver 会把检查点保存在当前 Python 进程内存里。
# 它适合学习和演示，不适合生产环境。
checkpointer = InMemorySaver()

agent = create_agent(
    model=model,
    tools=[get_weather],
    # 给 Agent 配 checkpointer 后，它就可以按 thread_id 保存对话状态。
    checkpointer=checkpointer,
)

# 同一个 thread_id 表示同一个对话线程。
config = {"configurable": {"thread_id": "thread-1"}}

agent.invoke(
    # 第一次运行：告诉 Agent 一个用户事实。
    {"messages": [{"role": "user", "content": "我叫小明"}]},
    config=config,
)

agent.invoke(
    # 第二次运行：同一个 thread_id，所以可以接上上一次状态。
    {"messages": [{"role": "user", "content": "我叫什么？"}]},
    config=config,
)
```

这段代码可以按步骤理解：

1. `InMemorySaver()`：创建一个本地内存检查点保存器。
2. `checkpointer=checkpointer`：让 Agent 每一步都能保存状态快照。
3. `thread_id="thread-1"`：指定当前会话线程。
4. 第一次 `invoke`：把“我叫小明”写入这个线程的状态。
5. 第二次 `invoke`：沿用同一个 `thread_id`，因此可以读取前面的对话状态。
6. 如果换一个 `thread_id`，就会变成另一个独立会话。

`thread_id` 相同，就会接上同一个对话线程。`InMemorySaver` 只适合学习和本地演示，生产环境要换成数据库或平台提供的持久化存储。

持久化与记忆常见用途：

- 基本运用：线程隔离的持久化层。
- 基本运用：跨线程持久化调用。
- 记忆：短期记忆的实现。
- 记忆：长期记忆及实现。
- 记忆：使用总结技术优化记忆。

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
    # 下面三个字段就是希望模型最终稳定返回的结构。
    city: str
    weather: str
    advice: str


agent = create_agent(
    model=model,
    tools=[get_weather],
    # response_format 会要求最终答案尽量符合 WeatherAnswer。
    response_format=WeatherAnswer,
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]}
)

# 结构化结果放在 structured_response 中，通常是 WeatherAnswer 实例或等价结构。
print(result["structured_response"])
```

这段代码可以按步骤理解：

1. `WeatherAnswer`：定义最终输出必须有哪些字段。
2. `response_format=WeatherAnswer`：让 Agent 在最终回答时产出结构化结果。
3. `result["structured_response"]`：读取结构化输出，比从自然语言里手动解析更稳定。
4. 结构化输出适合给前端、接口、表格或后续程序继续处理。

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
    # updates 表示每个节点完成后返回一次状态更新。
    stream_mode="updates",
):
    print(chunk)
```

LLM token 流：

```python
for token, metadata in agent.stream(
    {"messages": [{"role": "user", "content": "写一句问候语"}]},
    # messages 表示按模型 token 流式输出。
    stream_mode="messages",
):
    # token 是当前输出片段，metadata 里通常有节点名、运行信息等。
    print(token, metadata)
```

流式代码可以这样理解：

1. `stream_mode="updates"`：更适合看 Agent 执行到了哪个节点、工具调用是否完成。
2. `stream_mode="messages"`：更适合做聊天打字机效果。
3. `chunk` 或 `token` 都是边运行边返回的内容，不必等整个 Agent 结束。
4. 调试 Agent 时先看 `updates`，做用户界面时常用 `messages`。

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
    # interrupt 会暂停图执行，并把这段数据交给外部人工处理。
    review = interrupt(
        {
            "question": "是否允许发送邮件？",
            "draft": state["email_draft"],
        }
    )
    # 恢复后，review 会变成人工输入的结果。
    return {"approved": review["approved"]}


# Command(resume=...) 用来把人工审批结果送回暂停点。
graph.invoke(Command(resume={"approved": True}), config=config)
```

这段代码可以按步骤理解：

1. `approval_node(state)`：这是一个需要人工审批的图节点。
2. `interrupt(...)`：暂停执行，并把问题和草稿交给人工界面。
3. 人工处理完成后，用 `Command(resume=...)` 恢复图。
4. `review["approved"]`：读取人工审批结果，写回状态。
5. 这种流程必须配合 checkpointer，否则暂停后进程结束就无法恢复。

涉及高风险动作时，人工审批比单纯依赖 Prompt 更可靠。

## 十四、多智能体

当一个 Agent 工具太多、上下文太复杂或任务领域差异很大时，可以拆成多个专业 Agent。

### 为什么选择多智能体

| 对比项 | Single Agent | Multi Agents |
| --- | --- | --- |
| 系统结构 | 结构简单，只有一个智能体负责所有任务 | 系统由多个相互协作的智能体组成 |
| 专业分工 | 更适合相对简单或专一的任务 | 各 Agent 可以有不同专业领域或功能 |
| 决策协调 | 决策过程不需要协调多个 Agent 之间通信 | 需要 Agent 间通信和协调机制 |
| 执行效率 | 通常计算资源需求较少，响应速度可能更快 | 可以并行处理多个任务 |
| 系统能力 | 实现和调试成本较低 | 整体更复杂，但能力更强 |
| 扩展性 | 适合小规模或单一职责应用 | 有更好的可扩展性和容错能力 |
| 常见框架 | LangChain 内置单 Agent 能力 | LangGraph 内置多 Agent 编排能力 |

常见架构：

| 架构 | 含义 | 适合场景 |
| --- | --- | --- |
| Single Agent | 一个 Agent 负责所有工具调用和最终回答 | 简单问答、固定工具数量、任务边界明确 |
| 网络 | 每个 Agent 可以和其他 Agent 通信 | 灵活探索，但控制较难 |
| 主管 | 主管 Agent 决定调用哪个专家 Agent | 常见、易理解 |
| 主管工具调用 | 把专家 Agent 包装成工具给主管调用 | 工具调用模型表现好时很方便 |
| 分层 | 主管下面还有主管 | 大型复杂组织流程 |
| 自定义工作流 | 开发者明确限制哪些 Agent 能互相跳转 | 业务流程强约束 |

几种架构的直观理解：

- 网状结构：任何一个智能体都可以进行决策。
- 监督者结构：由主管来决策下一步操作。
- 监督者架构（工具）：智能体作为工具，接受一个 LLM 主管的调用。
- 分级架构：多级架构每级都有一个监督者。
- 自定义：只有部分智能体具备决策权。

多智能体的封装颗粒度更小，控制层级更低，因此更灵活，但实现难度也更高。不要一上来就拆很多 Agent，应该先根据职责边界、工具集合和上下文长度决定是否真的需要拆分。

交接可以用 `Command` 表示：

```python
from typing import Literal
from langgraph.types import Command


# 返回类型里的 Literal 用来限制 goto 只能跳到这些节点。
def router_agent(state) -> Command[Literal["research_agent", "math_agent", "__end__"]]:
    # decide_next_agent 是示意函数，实际项目里可以由规则或模型决定。
    next_agent = decide_next_agent(state)
    return Command(
        # goto 表示下一步跳到哪个 Agent 或节点。
        goto=next_agent,
        # update 表示同时写入状态更新。
        update={"last_router": "router_agent"},
    )
```

这段代码可以按步骤理解：

1. `Command[...]`：表示这个节点不只是返回状态，还会控制下一步跳转。
2. `Literal[...]`：限制允许跳转的目标节点，方便类型检查和阅读。
3. `decide_next_agent(state)`：根据当前状态决定交给研究 Agent、数学 Agent，还是结束。
4. `goto=next_agent`：告诉图下一步去哪里。
5. `update={...}`：顺手把路由信息写回状态，方便调试和追踪。

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

更具体地说：

| 核心组件 | 说明 |
| --- | --- |
| Node | 节点是图中的基本单元，代表一个具体功能或操作。每个节点负责完成一项特定任务，比如查询数据、生成文本、做决策等。节点接收输入，处理后产生输出，可以是简单函数、API 调用、LLM 调用或更复杂的业务操作。 |
| Graph | 图是节点及其连接关系的集合，代表整个工作流程。它定义信息如何从一个节点流向另一个节点，可以是线性的 `A -> B -> C`，也可以包含分支、循环和人工中断，用来控制整个应用的执行流程和逻辑。 |

最小图示例：

```python
from typing_extensions import TypedDict
from langgraph.graph import StateGraph, START, END


class State(TypedDict):
    # 输入问题，由调用 graph.invoke 时传入。
    question: str
    # 输出答案，由 answer_node 返回更新。
    answer: str


def answer_node(state: State):
    # 节点接收整个 state，返回一个“局部状态更新”字典。
    # 这里没有返回 question，因为 question 不需要修改。
    return {"answer": f"你问的是：{state['question']}"}


# 创建图构建器，并声明整张图共享的状态结构是 State。
builder = StateGraph(State)

# 注册一个节点，节点名叫 answer，执行函数是 answer_node。
builder.add_node("answer", answer_node)

# START 是特殊入口节点，表示图运行后第一步进入 answer。
builder.add_edge(START, "answer")

# answer 执行完后进入 END，表示流程结束。
builder.add_edge("answer", END)

# 编译后才会得到可运行的 graph。
graph = builder.compile()

# 传入初始 state，LangGraph 会从 START 开始执行。
result = graph.invoke({"question": "什么是 LangGraph？"})
```

这段代码可以按步骤理解：

1. `class State(TypedDict)`：定义整张图共享的状态结构，也就是图里会流转哪些字段。
2. `question: str`：输入字段，运行图时传入。
3. `answer: str`：输出字段，由节点执行后写入。
4. `answer_node(state: State)`：节点函数，接收当前状态。
5. `return {"answer": ...}`：节点返回局部更新，LangGraph 会把它合并回 state。
6. `builder = StateGraph(State)`：创建图构建器，并绑定状态 schema。
7. `builder.add_node("answer", answer_node)`：把 Python 函数注册成图节点。
8. `builder.add_edge(START, "answer")`：声明入口，从 `START` 进入 `answer`。
9. `builder.add_edge("answer", END)`：声明结束，`answer` 跑完后到 `END`。
10. `graph = builder.compile()`：把图构建器编译成可运行对象。
11. `graph.invoke(...)`：传入初始状态并执行整张图。

最容易出错的点是：节点不要直接返回字符串，要返回状态更新字典，例如 `{"answer": "..."}`。

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
    # Annotated 的第二个参数 add_messages 是 reducer。
    # 含义：新 messages 到来时追加到旧列表，而不是覆盖旧列表。
    messages: Annotated[list[AnyMessage], add_messages]
```

`add_messages` 表示新消息会追加到已有消息列表，而不是覆盖整个列表。

这段代码可以按步骤理解：

1. `messages`：保存聊天消息列表，是 Agent 最常见的状态字段。
2. `Annotated[list[AnyMessage], add_messages]`：给字段额外绑定合并规则。
3. `add_messages`：当节点返回新的消息时，会追加或按消息 ID 更新，而不是直接覆盖整个列表。
4. 如果不写 reducer，普通字段默认是“新值覆盖旧值”。
5. 并行分支同时写列表时尤其需要 reducer，否则很容易丢数据。

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

这行代码表示：`node_a` 运行结束后，固定进入 `node_b`，中间没有判断逻辑。

条件边适合分支：

```python
def route(state):
    # 根据当前状态决定下一步去哪个节点。
    if state["need_tool"]:
        return "tool_node"
    return "final_node"


# model_node 执行完以后，会调用 route(state) 获取下一步节点名。
builder.add_conditional_edges("model_node", route)
```

这段代码可以按步骤理解：

1. `route(state)`：路由函数，只负责判断下一步去哪。
2. `state["need_tool"]`：根据状态里的字段判断是否需要工具节点。
3. `return "tool_node"`：返回目标节点名。
4. `builder.add_conditional_edges("model_node", route)`：把条件路由挂到 `model_node` 后面。
5. 条件边适合做意图分类、是否调用工具、是否需要人工审批、是否结束等分支。

`Send` 适合动态并行分发，例如把一批文档分别交给多个节点处理。`Command` 适合把“更新状态”和“跳转节点”合在一起，常用于多代理交接、人工恢复和复杂控制流。

简化理解：

```text
add_edge：固定下一步。
add_conditional_edges：根据状态判断下一步。
Send：动态创建多个分支任务。
Command：一边更新状态，一边决定跳到哪里。
```

### MapReduce 并行执行

MapReduce 适合“先拆分，再并行处理，最后汇总”的任务。图片里的例子是：给定一个来自用户的一般主题，先生成相关主题列表，然后为每个主题生成一个笑话，最后从所有笑话中选择最佳笑话。

```text
topic
-> generate_topics
-> Send(generate_joke, subject_1)
-> Send(generate_joke, subject_2)
-> Send(generate_joke, subject_3)
-> reduce / best_joke
```

在 LangGraph 中通常会准备两类状态：

```text
Overall State:
subjects: [subject, subject, subject]
jokes: [joke, joke, joke]
best_joke: ...

Joke State:
subject: subject
joke: joke
```

其中 `generate_topics` 是 map 前的拆分步骤，`generate_joke` 是 map 阶段的并行节点，`best_joke` 是 reduce 阶段的汇总节点。多个 map 分支写回 `jokes` 时，通常要给列表字段配置 reducer，例如 `Annotated[list[str], operator.add]`，否则后返回的分支可能覆盖先返回的结果。

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

# 创建检查点保存器。
checkpointer = InMemorySaver()

# 编译图时传入 checkpointer，图运行过程中才会保存状态快照。
graph = builder.compile(checkpointer=checkpointer)

# thread_id 用来区分不同会话或不同任务实例。
config = {"configurable": {"thread_id": "demo-thread"}}

# 每次运行时带上同一个 config，就能接上同一个线程的状态。
graph.invoke({"question": "你好"}, config=config)
```

这段代码可以按步骤理解：

1. `InMemorySaver()`：把检查点存在内存中，适合本地学习。
2. `builder.compile(checkpointer=checkpointer)`：把检查点能力挂到图上。
3. `thread_id`：告诉 LangGraph 这是哪一个会话线程。
4. `graph.invoke(..., config=config)`：执行图时带上线程配置。
5. 相同 `thread_id` 会写入同一条历史，不同 `thread_id` 会彼此隔离。

注意：这个示例只用内存检查点，不会操作数据库。生产环境可以换持久化 checkpointer，但不要在学习文档里直接执行数据库迁移或清表操作。

持久化带来的能力：

- 多轮短期记忆。
- 人工参与循环。
- 失败后从检查点恢复。
- 查看历史状态。
- 时间旅行和分支调试。

更完整地说，持久化是 LangGraph 的内置能力，通过检查点器实现，它提供“保存和恢复图执行状态”的机制。这样 AI 应用可以记住之前的交互，也能在中断后从上次停止的地方继续执行，并为调试、回放和人机协作提供基础支持。

与普通聊天历史不同，检查点保存的是图运行状态：包括当前 state、下一步要执行的节点、任务信息和元数据。长期记忆则更像一个跨线程的资料库，用于保存用户偏好、稳定事实或业务资料。两者经常配合使用：检查点解决“这次流程运行到哪了”，长期记忆解决“这个用户以前告诉过我什么”。

## 十九、时间旅行

时间旅行指从之前的检查点恢复执行。它适合调试非确定性的 Agent，因为同一个问题可能因为模型输出不同走出不同路径。

用途：

- 回看 Agent 为什么调用某个工具。
- 从失败前的状态继续执行。
- 修改旧状态，尝试另一条路线。
- 比较不同 Prompt 或工具结果对流程的影响。

注意：从旧检查点恢复通常会形成新的执行分支，而不是覆盖原历史。

最小示例：先运行一张带检查点的图，再查看历史状态。

```python
from typing_extensions import TypedDict

from langgraph.checkpoint.memory import InMemorySaver
from langgraph.graph import END, START, StateGraph


class TravelState(TypedDict):
    # 输入问题。
    question: str
    # 中间草稿。
    draft: str
    # 最终答案。
    answer: str


def draft_node(state: TravelState) -> dict[str, str]:
    # 第一个节点生成草稿。
    return {"draft": f"草稿：正在回答 {state['question']}"}


def final_node(state: TravelState) -> dict[str, str]:
    # 第二个节点基于草稿生成最终答案。
    return {"answer": state["draft"].replace("草稿", "最终答案")}


builder = StateGraph(TravelState)
builder.add_node("draft", draft_node)
builder.add_node("final", final_node)
builder.add_edge(START, "draft")
builder.add_edge("draft", "final")
builder.add_edge("final", END)

# 时间旅行依赖检查点，所以 compile 时要传 checkpointer。
graph = builder.compile(checkpointer=InMemorySaver())

# thread_id 用来标识同一条运行历史。
config = {"configurable": {"thread_id": "travel-demo"}}

result = graph.invoke(
    {"question": "什么是时间旅行？", "draft": "", "answer": ""},
    config=config,
)

# get_state_history 可以查看这个 thread 的历史快照。
history = list(graph.get_state_history(config))

for snapshot in history:
    print("下一步节点：", snapshot.next)
    print("当前状态：", snapshot.values)
```

这段代码可以按步骤理解：

1. `InMemorySaver()`：保存每一步状态快照。
2. `thread_id="travel-demo"`：指定要查看哪条运行历史。
3. `graph.invoke(..., config=config)`：执行图，并把过程写入检查点。
4. `graph.get_state_history(config)`：读取历史状态快照。
5. `snapshot.values`：当时的状态值。
6. `snapshot.next`：当时下一步准备执行的节点。

如果要从某个历史快照继续运行，通常会拿到对应 snapshot 的配置或 checkpoint 信息，再用同一个图继续执行。学习阶段先会“查看历史”，再学习“从历史分支恢复”，会更稳。

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

示例一：父图和子图共享状态字段，直接把子图作为节点使用。

```python
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph


class SharedState(TypedDict):
    # 父图和子图都能读取 topic。
    topic: str
    # 子图写入 outline。
    outline: str
    # 父图最后写入 answer。
    answer: str


def make_outline(state: SharedState) -> dict[str, str]:
    # 子图节点：生成大纲。
    return {"outline": f"{state['topic']} 的三个要点"}


# 先创建子图。
sub_builder = StateGraph(SharedState)
sub_builder.add_node("make_outline", make_outline)
sub_builder.add_edge(START, "make_outline")
sub_builder.add_edge("make_outline", END)
outline_graph = sub_builder.compile()


def write_answer(state: SharedState) -> dict[str, str]:
    # 父图节点：使用子图生成的 outline 写最终答案。
    return {"answer": f"根据大纲回答：{state['outline']}"}


# 再创建父图。
parent_builder = StateGraph(SharedState)

# 子图可以像普通节点一样加入父图。
parent_builder.add_node("outline_subgraph", outline_graph)
parent_builder.add_node("write_answer", write_answer)
parent_builder.add_edge(START, "outline_subgraph")
parent_builder.add_edge("outline_subgraph", "write_answer")
parent_builder.add_edge("write_answer", END)

parent_graph = parent_builder.compile()

result = parent_graph.invoke(
    {"topic": "LangGraph 子图", "outline": "", "answer": ""}
)
print(result)
```

这段代码可以按步骤理解：

1. `SharedState`：父图和子图使用同一个状态结构。
2. `outline_graph = sub_builder.compile()`：先把子流程编译成子图。
3. `parent_builder.add_node("outline_subgraph", outline_graph)`：把子图注册为父图节点。
4. 父图先执行子图，子图写入 `outline`。
5. 父图再执行 `write_answer`，根据 `outline` 写入 `answer`。

示例二：父图和子图状态不同，在父图节点里手动调用子图并做转换。

```python
from typing_extensions import TypedDict

from langgraph.graph import END, START, StateGraph


class ChildState(TypedDict):
    text: str
    summary: str


def summarize_child(state: ChildState) -> dict[str, str]:
    # 子图只关心 text 和 summary。
    return {"summary": state["text"][:20] + "..."}


child_builder = StateGraph(ChildState)
child_builder.add_node("summarize", summarize_child)
child_builder.add_edge(START, "summarize")
child_builder.add_edge("summarize", END)
child_graph = child_builder.compile()


class ParentState(TypedDict):
    document: str
    child_summary: str


def call_child_graph(state: ParentState) -> dict[str, str]:
    # 父图把 document 转成子图需要的 text。
    child_result = child_graph.invoke(
        {"text": state["document"], "summary": ""}
    )
    # 再把子图 summary 转回父图字段 child_summary。
    return {"child_summary": child_result["summary"]}


parent_builder = StateGraph(ParentState)
parent_builder.add_node("call_child", call_child_graph)
parent_builder.add_edge(START, "call_child")
parent_builder.add_edge("call_child", END)

parent_graph = parent_builder.compile()
parent_graph.invoke({"document": "这是一段很长很长的文档内容，用来演示子图状态转换。", "child_summary": ""})
```

这段代码可以按步骤理解：

1. `ChildState` 和 `ParentState` 不一样，不能直接共享状态。
2. `call_child_graph` 是父图里的普通节点。
3. 在节点内部调用 `child_graph.invoke(...)`。
4. 调用前把父图字段 `document` 转成子图字段 `text`。
5. 调用后把子图字段 `summary` 转回父图字段 `child_summary`。

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

最小示例：用 `@task` 定义步骤，用 `@entrypoint` 定义入口。

```python
from langgraph.func import entrypoint, task


@task
def generate_outline(topic: str) -> str:
    # task 表示一个可被 LangGraph 管理的任务步骤。
    return f"{topic}：概念、用法、注意事项"


@task
def write_summary(outline: str) -> str:
    # 另一个任务，输入来自上一个任务结果。
    return f"根据大纲生成摘要：{outline}"


@entrypoint()
def article_workflow(topic: str) -> str:
    # 调用 task 后通常要用 .result() 获取任务结果。
    outline = generate_outline(topic).result()
    summary = write_summary(outline).result()
    return summary


result = article_workflow.invoke("LangGraph 函数式 API")
print(result)
```

这段代码可以按步骤理解：

1. `@task`：把普通函数声明为 LangGraph 可管理任务。
2. `@entrypoint()`：声明整个工作流入口。
3. `generate_outline(topic).result()`：执行任务并取结果。
4. `write_summary(outline).result()`：把上一步结果传给下一步。
5. `article_workflow.invoke(...)`：像调用 Runnable 一样执行函数式工作流。

函数式 API 适合流程比较像普通 Python 代码的场景；如果流程有很多分支、循环、可视化调试需求，`StateGraph` 往往更清楚。

如果要加入持久化，可以给入口配置 checkpointer：

```python
from langgraph.checkpoint.memory import InMemorySaver


@entrypoint(checkpointer=InMemorySaver())
def durable_workflow(topic: str) -> str:
    outline = generate_outline(topic).result()
    return write_summary(outline).result()


config = {"configurable": {"thread_id": "func-demo"}}
durable_workflow.invoke("可持久化函数式工作流", config=config)
```

这段代码的重点是：函数式 API 也可以使用 `thread_id` 和检查点能力，只是写法更接近普通函数。

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

离线评估示例：先写一个被评估的 Agent/函数，再写评估器。

```python
def weather_agent(question: str) -> dict:
    """离线模拟一个天气 Agent 的输出。"""

    if "天气" in question:
        return {
            "answer": "上海今天晴，适合出门。",
            "tool_calls": ["get_weather"],
        }

    return {
        "answer": "我只能回答天气相关问题。",
        "tool_calls": [],
    }


def evaluate_weather_case(example: dict) -> dict:
    # inputs 是测试输入。
    question = example["input"]
    # expected_tool 是期望 Agent 调用的工具。
    expected_tool = example["expected_tool"]
    # must_contain 是答案里必须包含的关键词。
    must_contain = example["must_contain"]

    output = weather_agent(question)

    tool_ok = expected_tool in output["tool_calls"] if expected_tool else not output["tool_calls"]
    answer_ok = must_contain in output["answer"]

    return {
        "question": question,
        "tool_ok": tool_ok,
        "answer_ok": answer_ok,
        "passed": tool_ok and answer_ok,
        "output": output,
    }


examples = [
    {
        "input": "上海天气怎么样？",
        "expected_tool": "get_weather",
        "must_contain": "上海",
    },
    {
        "input": "你会写代码吗？",
        "expected_tool": None,
        "must_contain": "天气",
    },
]

for example in examples:
    print(evaluate_weather_case(example))
```

这段代码可以按步骤理解：

1. `weather_agent(question)`：被评估对象，可以是真实 Agent，也可以是离线模拟。
2. `examples`：评估集，每条包含输入和期望行为。
3. `expected_tool`：检查工具调用是否正确。
4. `must_contain`：检查最终答案是否包含关键信息。
5. `passed`：把多个指标合成一个是否通过的结果。

LangGraph / Agent 的评估不要只看最终文本，还要看过程是否正确。例如天气问题是否真的调用天气工具，删除数据前是否真的暂停审批，RAG 回答是否引用了正确来源。

更接近生产的评估可以拆成多个 evaluator：

```python
def tool_call_evaluator(output: dict, expected_tool: str | None) -> bool:
    # 判断工具调用是否符合预期。
    if expected_tool is None:
        return not output["tool_calls"]
    return expected_tool in output["tool_calls"]


def answer_contains_evaluator(output: dict, keyword: str) -> bool:
    # 判断答案是否包含关键事实。
    return keyword in output["answer"]


output = weather_agent("上海天气怎么样？")
print(tool_call_evaluator(output, "get_weather"))
print(answer_contains_evaluator(output, "上海"))
```

项目里可以把这些 evaluator 接到 LangSmith Evaluation，用真实数据集持续评估 Agent 质量。

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

## 二十五、LangGraph 应用、工具与 Studio

这一节偏工程化：把图、工具、配置和本地调试服务组织成一个可以用 Studio 查看和测试的 LangGraph 应用。

### 创建 LangGraph 应用

常见流程：

```bash
# Python 版本建议使用 3.11 及以上。
pip install -U "langgraph-cli[inmem]"

# 使用官方 Python 模板创建 LangGraph 应用。
langgraph new path/to/your/app --template new-langgraph-project-python
```

如果不指定模板，`langgraph new` 会进入交互式选择。学习阶段建议先用 Python 模板，生成后再按自己的业务拆分。

典型项目结构：

```text
my-app/
├─ src/
│  └─ agent/
│     ├─ tools/
│     │  ├─ __init__.py
│     │  ├─ calculator.py
│     │  └─ search.py
│     ├─ __init__.py
│     ├─ graph.py      # 构建并导出 graph
│     ├─ nodes.py      # 节点函数
│     └─ state.py      # State 定义
├─ .env                # 环境变量
├─ langgraph.json      # LangGraph 配置
└─ pyproject.toml      # 项目依赖
```

`langgraph.json` 告诉本地服务器和 Studio：依赖从哪里装，图入口在哪里，环境变量文件在哪里。

```json
{
  "dependencies": ["."],
  "graphs": {
    "agent": "./src/agent/graph.py:graph"
  },
  "env": ".env"
}
```

`"agent": "./src/agent/graph.py:graph"` 表示：Studio 中图的名字叫 `agent`，代码入口是 `src/agent/graph.py` 文件里的 `graph` 变量。这个变量通常是 `builder.compile()` 或 `create_agent(...)` 返回的可运行图。

模板项目通常使用 `pyproject.toml` 管理依赖。开发时可以在项目根目录安装本地包：

```bash
pip install -e .
```

如果是在 AutoDL 这类远程算力环境中开发，本质步骤不变：创建虚拟环境、安装依赖、配置 `.env`、启动 `langgraph dev`。区别只是访问 Studio 或 API 时可能需要平台提供的端口转发。

### 启动本地服务与 Studio

在包含 `langgraph.json` 的项目根目录运行：

```bash
langgraph dev
```

启动成功后通常会输出三类地址：

```text
API: http://127.0.0.1:2024
Studio UI: https://smith.langchain.com/studio/?baseUrl=http://127.0.0.1:2024
API Docs: http://127.0.0.1:2024/docs
```

含义：

- `API`：本地 Agent Server 地址，可以用 HTTP 请求调用。
- `Studio UI`：LangGraph Studio，可视化查看图结构、输入输出、线程、interrupt 和 memory。
- `API Docs`：本地接口文档，适合测试请求格式。

Studio 里常见区域：

- `Graph`：查看 `START -> agent -> tools -> END` 这类图结构。
- `Chat`：用对话形式测试 Agent。
- `Input`：手动构造 graph 输入，例如 `messages`、`remaining_steps` 等字段。
- `Memory`：查看与线程或用户相关的记忆。
- `Interrupts`：查看等待人工处理的中断点。

如果 Studio 顶部提示缺少 `LANGSMITH_API_KEY`，通常不影响本地看图和测试接口；如果想把运行记录同步到 LangSmith，则需要在 `.env` 中补充对应 key。

推荐调试顺序：

1. 写好 `graph.py`，确保导出变量名和 `langgraph.json` 中一致。
2. 写好 `.env`，例如百炼/OpenAI 兼容模式需要 `DASHSCOPE_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`；如果使用 DeepSeek 官方封装，再配置 `DEEPSEEK_API_KEY`、`DEEPSEEK_API_BASE`；可选 `LANGSMITH_API_KEY`。
3. 在项目根目录运行 `langgraph dev`。
4. 打开终端输出的 Studio UI。
5. 在 `Graph` 视图确认节点和边是否符合预期。
6. 在 `Chat` 或 `Input` 中提交测试输入。
7. 如果图暂停在 `interrupt`，到 `Interrupts` 里处理人工输入。
8. 查看每一步的 state、messages、tool_calls 和工具返回。

### Tool 工具的定义

Agent 的工具列表不只是函数本身，还包含模型理解工具所需的元信息。

| 属性 | 类型 | 作用 |
| --- | --- | --- |
| `name` | `str` | 工具名，在提供给 LLM 或代理的一组工具中必须唯一 |
| `description` | `str` | 描述工具的作用，会被 LLM 或代理用作上下文 |
| `args_schema` | `pydantic.BaseModel` | 可选但推荐，描述参数结构，复杂参数和回调处理时尤其重要 |
| `return_direct` | `bool` | 为 `True` 时，工具返回后可直接作为最终结果返回给用户 |

工具定义建议：

- 工具名要清晰稳定，例如 `calculate`、`search_weather`、`get_order_detail`。
- 描述要写清楚“什么时候用”和“返回什么”。
- 参数要有类型注解；复杂参数用 Pydantic `BaseModel`。
- 不要把 `user_id`、token、权限等内部参数暴露给模型填写，应从 `ToolRuntime.context` 或后端会话中读取。
- 工具要写状态时返回 `Command(update=...)`；如果同时更新 `messages`，补上带 `tool_call_id` 的 `ToolMessage`。

方式一：从函数创建工具，适合最常见场景。

```python
from typing import Annotated
from langchain_core.tools import tool


def calculate_impl(a: float, b: float, operation: str) -> float:
    """普通 Python 实现函数，后面不同工具写法都复用它。"""

    match operation:
        case "add":
            return a + b
        case "subtract":
            return a - b
        case "multiply":
            return a * b
        case "divide":
            if b == 0:
                raise ValueError("除数不能为 0")
            return a / b
        case _:
            raise ValueError(f"不支持的运算类型：{operation}")


@tool("calculate")
def calculate(
    a: Annotated[float, "第一个需要输入的数字。"],
    b: Annotated[float, "第二个需要输入的数字。"],
    operation: Annotated[
        str,
        "运算类型，只能是 add、subtract、multiply、divide 中的任意一个。",
    ],
) -> float:
    """工具函数：计算两个数字的运算结果。"""
    return calculate_impl(a, b, operation)
```

方式二：使用 Pydantic `args_schema`，适合参数较多或需要更清晰描述的工具。

```python
from pydantic import BaseModel, Field
from langchain_core.tools import tool


class CalculateArgs(BaseModel):
    a: float = Field(description="第一个需要输入的数字。")
    b: float = Field(description="第二个需要输入的数字。")
    operation: str = Field(
        description="运算类型，只能是 add、subtract、multiply、divide 中的任意一个。"
    )


@tool("calculate", args_schema=CalculateArgs)
def calculate_with_schema(a: float, b: float, operation: str) -> float:
    """工具函数：计算两个数字的运算结果。"""
    return calculate_impl(a, b, operation)
```

方式三：使用 `StructuredTool.from_function`，适合需要显式设置工具名、描述、`return_direct` 或异步实现的场景。

```python
from langchain_core.tools import StructuredTool


async def async_calculate(a: float, b: float, operation: str) -> float:
    return calculate_impl(a, b, operation)


calculator = StructuredTool.from_function(
    func=calculate_impl,
    coroutine=async_calculate,
    name="calculator",
    description="工具函数：计算两个数字的运算结果。",
    args_schema=CalculateArgs,
    return_direct=False,
)
```

方式四：从 `Runnable` 转成工具，适合你已经有 LangChain Runnable 链，需要作为 Agent 工具复用的情况。

```python
from pydantic import BaseModel, Field


class SearchDocsArgs(BaseModel):
    query: str = Field(description="要搜索的问题或关键词")


tool = runnable.as_tool(
    name="search_docs",
    description="搜索项目文档并返回相关片段。",
    args_schema=SearchDocsArgs,
)
```

方式五：继承 `BaseTool`，适合工具内部要长期持有客户端、连接池或复杂配置的情况。

```python
from typing import Type

from langchain_core.tools import BaseTool
from pydantic import BaseModel, Field


class SearchArgs(BaseModel):
    query: str = Field(description="搜索关键词")


class SearchTool(BaseTool):
    name: str = "search_tool"
    description: str = "调用外部搜索服务，并返回摘要结果。"
    args_schema: Type[BaseModel] = SearchArgs
    return_direct: bool = False

    def _run(self, query: str) -> str:
        return f"搜索结果：{query}"
```

如果你在截图或旧代码里看到没有类型注解的 `name = "search_tool"`、`args_schema = SearchArgs`，新版环境可能会报 Pydantic 字段覆盖错误。按上面这样补 `name: str`、`args_schema: Type[BaseModel]` 即可。

方式六：工具读取运行时上下文或更新状态，用 `ToolRuntime`。

```python
from langchain.tools import ToolRuntime, tool
from langchain_core.messages import ToolMessage
from langgraph.types import Command


@tool
def set_username(runtime: ToolRuntime) -> Command:
    username = runtime.context.user_name
    return Command(
        update={
            "username": username,
            "messages": [
                ToolMessage(
                    content=f"当前用户名是 {username}",
                    tool_call_id=runtime.tool_call_id,
                )
            ],
        }
    )
```

优先使用 `ToolRuntime`，不要继续照抄旧示例里的 `InjectedToolCallId`。`ToolRuntime` 同时覆盖 context、state、store 和 tool_call_id，代码更集中，也更贴近当前文档。

常见问题：

- Studio 看不到图：检查 `langgraph.json` 的 `graphs` 路径和变量名是否正确。
- API 能启动但模型报错：检查 `.env` 中模型 key、base URL、模型名。
- 工具不被调用：检查工具描述是否清楚、模型是否支持 tool calling、参数 schema 是否合理。
- 本地端口打不开：确认 `langgraph dev` 仍在运行；远程服务器需要端口转发。

## 二十六、常见错误与排查

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
| `create_react_agent` 弃用警告 | 还在从 `langgraph.prebuilt` 导入旧入口 | 改用 `from langchain.agents import create_agent` |
| `InjectedToolCallId` 等旧注入写法不兼容 | 旧版教程或迁移期代码 | 改用 `from langchain.tools import ToolRuntime` |
| `BaseTool` 类字段报 Pydantic 错误 | `name`、`description`、`args_schema` 没有类型注解 | 写成 `name: str = ...`、`args_schema: Type[BaseModel] = ...` |
| 工具调用本地模型失败 | 模型不支持 tool calling，或本地服务 tool-call parser 不匹配 | 检查模型能力、vLLM/SGLang parser、关闭不兼容的 thinking/streaming |
| `configurable` 里塞了业务用户信息 | 混淆了运行配置和业务上下文 | 用户、租户、权限放 `context_schema/context`；`thread_id` 放 `configurable` |

## 二十七、学习路线与小抄

建议顺序：

1. 先会用 `create_agent` 创建工具调用 Agent。
2. 掌握 `invoke`、`stream`、`messages` 输入输出。
3. 学会配置模型、Prompt、工具和结构化输出。
4. 加入 checkpointer 和 `thread_id`，理解短期记忆。
5. 学习 `StateGraph`、`State`、`Node`、`Edge`。
6. 学习条件边、reducer、`Command`。
7. 学习人工参与循环和时间旅行。
8. 学习多代理、子图和部署。

可以按下面这些小练习补充巩固：

- LangGraph HelloWorld。
- 基本控制：串行控制。
- 基本控制：分支控制。
- 基本控制：条件分支与循环。
- 基本控制：图的可视化。
- 精细控制：图的运行时配置。
- 精细控制：map-reduce。
- 持久化：线程隔离的持久化层。
- 持久化：跨线程持久化调用。
- 记忆：短期记忆实现。
- 记忆：长期记忆实现。
- 记忆：使用总结技术优化记忆。

常用小抄：

```python
# 预构建 Agent
agent = create_agent(
    # Agent 使用的模型。
    model=model,
    # Agent 能调用的工具列表。
    tools=[get_weather],
    # 可选：加入检查点后支持短期记忆和恢复。
    checkpointer=checkpointer,
)

result = agent.invoke(
    # Agent 输入通常放在 messages 里。
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]},
    # thread_id 用来区分不同对话线程。
    config={"configurable": {"thread_id": "thread-1"}},
)

# 工具读取运行时 context
agent.invoke(
    {"messages": [{"role": "user", "content": "查询当前用户资料"}]},
    # context 适合传 user_id、权限、租户等后端已知信息。
    context=Context(user_id="U001"),
)

# 最小状态图
# 创建图构建器
builder = StateGraph(State)

# 添加节点
builder.add_node("answer", answer_node)

# 设置入口边
builder.add_edge(START, "answer")

# 设置结束边
builder.add_edge("answer", END)

# 编译成可运行图
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

## 二十八、官方参考

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


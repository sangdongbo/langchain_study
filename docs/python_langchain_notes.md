# Python 与 LangChain 常用知识点整理

本文档用于快速复习 Python 基础语法、AI 应用开发基础，以及 LangChain 中常用的模型、提示词、链、工具、智能体、记忆和 RAG 知识点。内容按功能重新整理：相同主题集中在一起，先 Python，后大模型，再 LangChain，最后 RAG 项目实战。

## 一、Python 基础语法

### 1. 字面量、变量与数据类型

字面量是代码中直接写出的值，例如 `10`、`3.14`、`"Python"`、`True`、`None`。

变量用于保存数据，Python 使用 `变量名 = 值` 赋值。

```python
name = "Alice"
age = 18
price = 19.9
is_active = True
empty_value = None
```

常见数据类型：

| 类型 | 示例 | 说明 |
| --- | --- | --- |
| `int` | `18` | 整数 |
| `float` | `3.14` | 小数 |
| `str` | `"hello"` | 字符串 |
| `bool` | `True` / `False` | 布尔值 |
| `NoneType` | `None` | 空值 |
| `list` | `[1, 2, 3]` | 列表 |
| `dict` | `{"name": "Tom"}` | 字典 |
| `tuple` | `(1, 2)` | 元组 |
| `set` | `{1, 2, 3}` | 集合 |

注意：

- Python 是动态类型语言，变量本身不固定类型。
- 变量必须先赋值再使用。
- 重新赋值会覆盖旧值。
- 可以连续赋值或一次定义多个变量。

```python
a = b = 10
x, y = 1, "Python"
```

### 2. 字符串

字符串可以使用单引号、双引号或三引号。

```python
s1 = 'hello'
s2 = "hello"
s3 = """多行字符串"""
```

常见写法：

```python
name = "Alice"
age = 18

print("姓名：" + name)
print(f"姓名：{name}，年龄：{age}")
print("姓名：{}，年龄：{}".format(name, age))
```

常用方法：

```python
text = " Python,LangChain,RAG "

print(text.strip())              # 去掉两端空白
print(text.lower())              # 转小写
print(text.upper())              # 转大写
print(text.replace("RAG", "AI"))
print(text.split(","))           # 按分隔符拆分
print("Python" in text)          # 判断是否包含
```

### 3. 输入、输出与类型转换

`input()` 获取用户输入，返回值一定是字符串。

```python
age = input("请输入年龄：")
age = int(age)
print(age + 1)
```

常见类型转换：

```python
int("10")
float("3.14")
str(100)
bool(1)
list("abc")
```

### 4. 运算符

常见运算符：

| 类型 | 示例 | 说明 |
| --- | --- | --- |
| 算术运算 | `+ - * / // % **` | 加减乘除、整除、取余、幂 |
| 比较运算 | `== != > >= < <=` | 返回布尔值 |
| 逻辑运算 | `and or not` | 组合条件 |
| 成员运算 | `in` / `not in` | 判断元素是否存在 |
| 赋值运算 | `= += -= *=` | 赋值和复合赋值 |

```python
score = 85
if score >= 60 and score <= 100:
    print("成绩有效")
```

## 二、流程控制

### 1. if 条件判断

```python
score = 88

if score >= 90:
    print("优秀")
elif score >= 60:
    print("及格")
else:
    print("不及格")
```

注意：

- 条件后面必须有冒号。
- Python 使用缩进表示代码块。
- `elif` 可以有多个，`else` 最多一个。

### 2. match...case 模式匹配

`match...case` 适合处理多个固定分支。

```python
command = "start"

match command:
    case "start":
        print("启动")
    case "stop":
        print("停止")
    case _:
        print("未知命令")
```

`case _` 表示默认分支。

### 3. for 循环

```python
names = ["Tom", "Jerry", "Alice"]

for name in names:
    print(name)
```

配合 `enumerate()` 获取下标：

```python
for index, name in enumerate(names):
    print(index, name)
```

### 4. while 循环

`while` 会在条件成立时反复执行。

```python
count = 0

while count < 3:
    print(count)
    count += 1
```

`while...else`：循环正常结束时执行 `else`，如果被 `break` 打断则不执行。

```python
count = 0

while count < 3:
    count += 1
else:
    print("循环正常结束")
```

常见控制语句：

| 语句 | 作用 |
| --- | --- |
| `break` | 结束整个循环 |
| `continue` | 跳过本轮，进入下一轮 |
| `else` | 循环正常结束后执行 |

### 5. range

`range()` 常用于生成整数序列。

```python
range(5)        # 0, 1, 2, 3, 4
range(1, 5)     # 1, 2, 3, 4
range(1, 10, 2) # 1, 3, 5, 7, 9
```

```python
for i in range(1, 6):
    print(i)
```

## 三、容器数据结构

### 1. list 列表

列表有序、可变，可以存放任意类型。

```python
items = ["Python", "LangChain", "RAG"]

items.append("Agent")
items.insert(1, "LLM")
items.remove("RAG")
last = items.pop()
```

常见操作：

```python
print(items[0])      # 第一个元素
print(items[-1])     # 最后一个元素
print(len(items))    # 长度
print("Python" in items)
```

列表切片：

```python
nums = [0, 1, 2, 3, 4, 5]

print(nums[1:4])   # [1, 2, 3]
print(nums[:3])    # [0, 1, 2]
print(nums[3:])    # [3, 4, 5]
print(nums[::-1])  # 反转
```

列表推导式：

```python
squares = [x * x for x in range(5)]
evens = [x for x in range(10) if x % 2 == 0]
```

### 2. dict 字典

字典使用键值对存储数据，适合表达结构化信息。

```python
user = {
    "name": "Alice",
    "age": 18,
}

print(user["name"])
print(user.get("city", "未知"))

user["age"] = 19
user["city"] = "Shanghai"
```

遍历字典：

```python
for key, value in user.items():
    print(key, value)
```

常用方法：

| 方法 | 作用 |
| --- | --- |
| `get()` | 安全获取值 |
| `keys()` | 获取所有键 |
| `values()` | 获取所有值 |
| `items()` | 获取键值对 |
| `pop()` | 删除并返回值 |

### 3. tuple 元组

元组有序、不可变，适合保存不希望被修改的数据。

```python
point = (10, 20)
x, y = point
```

只有一个元素的元组必须加逗号：

```python
single = (1,)
```

### 4. set 集合

集合无序、不重复，适合去重和集合运算。

```python
nums = {1, 2, 2, 3}
print(nums)  # {1, 2, 3}
```

集合运算：

```python
a = {1, 2, 3}
b = {3, 4, 5}

print(a | b)  # 并集
print(a & b)  # 交集
print(a - b)  # 差集
```

### 5. 可变与不可变

| 类型 | 是否可变 |
| --- | --- |
| `list` | 可变 |
| `dict` | 可变 |
| `set` | 可变 |
| `str` | 不可变 |
| `tuple` | 不可变 |
| `int` / `float` / `bool` | 不可变 |

可变对象作为函数参数时要小心，因为函数内部修改会影响外部对象。

```python
def add_item(items):
    items.append("new")

values = []
add_item(values)
print(values)  # ["new"]
```

### 6. 容器选择建议

| 场景 | 推荐类型 |
| --- | --- |
| 有序、经常增删 | `list` |
| 键值映射 | `dict` |
| 固定结构、不希望修改 | `tuple` |
| 去重、集合运算 | `set` |
| 文本内容 | `str` |

## 四、函数、模块与面向对象

### 1. 函数

函数用于封装可复用逻辑。

```python
def greet(name: str) -> str:
    return f"Hello, {name}"

message = greet("Alice")
print(message)
```

参数常见形式：

```python
def create_user(name, age=18):
    return {"name": name, "age": age}
```

### 2. 类型注解

类型注解能提升代码可读性，也方便编辑器检查。

```python
def add(a: int, b: int) -> int:
    return a + b

names: list[str] = ["Tom", "Alice"]
user: dict[str, str | int] = {"name": "Tom", "age": 18}
```

### 3. dataclass

`dataclass` 适合定义简单数据对象。

```python
from dataclasses import dataclass

@dataclass
class User:
    name: str
    age: int

user = User(name="Alice", age=18)
print(user.name)
```

### 4. 模块导入

```python
import os
from pathlib import Path
from dataclasses import dataclass
```

本地模块通常按项目结构导入。建议把可复用代码放到独立文件中，避免一个脚本越来越长。

### 5. 异常处理

```python
try:
    value = int("abc")
except ValueError as exc:
    print("转换失败：", exc)
else:
    print("转换成功")
finally:
    print("无论是否异常都会执行")
```

## 五、文件、环境变量与 JSON

### 1. pathlib 处理路径

```python
from pathlib import Path

root = Path(__file__).parent
file_path = root / "data" / "demo.txt"

content = file_path.read_text(encoding="utf-8")
file_path.write_text("hello", encoding="utf-8")
```

`pathlib` 比字符串拼路径更稳，跨平台也更清晰。

### 2. 环境变量

API Key、模型配置等敏感信息不应写死在代码里，通常放到环境变量或 `.env` 文件中。

```python
import os

api_key = os.getenv("OPENAI_API_KEY")
if not api_key:
    raise RuntimeError("缺少 OPENAI_API_KEY")
```

常见习惯：

- `.env` 保存本地开发配置。
- `.env` 不提交到 Git。
- 线上环境使用部署平台的环境变量配置。

### 3. JSON 序列化与反序列化

JSON 常用于配置、接口传输和消息保存。

```python
import json

user = {"name": "Alice", "age": 18}

text = json.dumps(user, ensure_ascii=False, indent=2)
data = json.loads(text)
```

读写 JSON 文件：

```python
from pathlib import Path
import json

path = Path("user.json")
path.write_text(json.dumps(user, ensure_ascii=False, indent=2), encoding="utf-8")

loaded = json.loads(path.read_text(encoding="utf-8"))
```

## 六、AI 应用与大模型基础

### 1. 大模型部署方案

常见部署方式：

| 方式 | 特点 | 适合场景 |
| --- | --- | --- |
| 云端 API | 接入简单，效果稳定 | 快速开发、生产应用 |
| 本地模型 | 数据可控，无需外部 API | 学习、内网、隐私场景 |
| 私有化部署 | 可控性强，成本和运维更高 | 企业内部系统 |

### 2. Ollama 本地模型

Ollama 可用于本地运行模型。

常用命令示例：

```powershell
ollama pull qwen2.5
ollama run qwen2.5
ollama list
```

在 LangChain 中调用 Ollama 时，通常使用对应集成包或 `init_chat_model` 统一初始化。

### 3. HTTP API 与大模型交互

很多模型服务本质上都是 HTTP API。

```python
import requests

response = requests.post(
    "https://api.example.com/chat",
    headers={"Authorization": "Bearer YOUR_API_KEY"},
    json={"messages": [{"role": "user", "content": "你好"}]},
    timeout=30,
)

print(response.json())
```

真实项目要注意超时、重试、异常处理和日志脱敏。

### 4. 提示词工程

提示词工程的目标是让模型更稳定地完成任务。

常见原则：

- 明确角色：告诉模型扮演谁。
- 明确任务：说明要完成什么。
- 明确约束：说明不能做什么。
- 明确输出格式：例如 JSON、表格、列表。
- 提供示例：减少模型理解偏差。

### 5. Zero-shot 与 Few-shot

Zero-shot：不给示例，直接让模型完成任务。

```text
请把下面这句话分类为“正面”或“负面”：这件衣服质量很好。
```

Few-shot：给几个示例后再让模型完成任务。

```text
示例1：质量很好 -> 正面
示例2：物流太慢 -> 负面

请分类：这件衣服穿起来很舒服。
```

Few-shot 通常能提升格式稳定性和任务理解效果。

## 七、LangChain 基础与模型调用

### 1. LangChain 是什么

LangChain 是一个用于构建大模型应用的框架。它提供了模型调用、提示词模板、输出解析、工具调用、智能体、记忆、文档加载、检索和 RAG 等能力。

常见模块：

| 模块 | 作用 |
| --- | --- |
| Models | 调用聊天模型、Embedding 模型等 |
| Prompts | 管理提示词模板 |
| Output Parsers | 解析模型输出 |
| Runnables / LCEL | 把组件组合成链 |
| Tools | 封装外部能力 |
| Agents | 让模型自主选择工具和步骤 |
| Retrievers | 从知识库检索资料 |
| Vector Stores | 存储和查询向量 |

### 2. 依赖与导入习惯

LangChain 生态拆分较多，常见包包括：

```text
langchain
langchain-core
langchain-community
langchain-openai
langchain-text-splitters
langchain-chroma
```

学习和项目中经常看到这些导入：

```python
from langchain.chat_models import init_chat_model
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnableLambda, RunnablePassthrough
```

版本迭代较快，如果导入路径报错，优先查看官方文档或当前项目依赖版本。

### 3. 使用 init_chat_model

`init_chat_model` 可以用统一方式初始化不同供应商的聊天模型。

```python
from langchain.chat_models import init_chat_model

model = init_chat_model(
    "openai:gpt-4o-mini",
    temperature=0,
)

response = model.invoke("你好，请用一句话介绍 LangChain")
print(response.content)
```

常见参数：

| 参数 | 作用 |
| --- | --- |
| `model` | 模型名称 |
| `temperature` | 随机性，越低越稳定 |
| `max_tokens` | 最大输出长度 |
| `timeout` | 请求超时 |

### 4. 消息格式

聊天模型通常接收消息列表。

```python
from langchain_core.messages import HumanMessage, SystemMessage

messages = [
    SystemMessage(content="你是一个严谨的 Python 老师。"),
    HumanMessage(content="解释一下 list 和 tuple 的区别。"),
]

response = model.invoke(messages)
print(response.content)
```

常见消息类型：

| 类型 | 说明 |
| --- | --- |
| `SystemMessage` | 系统角色、约束、背景 |
| `HumanMessage` | 用户输入 |
| `AIMessage` | 模型回复 |
| `ToolMessage` | 工具执行结果 |

### 5. 模型类型选择

| 类型 | 作用 | 示例场景 |
| --- | --- | --- |
| Chat Model | 对话和文本生成 | 问答、客服、总结 |
| Embedding Model | 文本向量化 | RAG、相似度搜索 |
| Rerank Model | 检索结果重排 | 提升 RAG 命中质量 |
| Image / Multimodal Model | 图像理解或生成 | 图片问答、多模态应用 |

## 八、Prompt 模板与输出解析

### 1. PromptTemplate

`PromptTemplate` 适合普通字符串模板。

```python
from langchain_core.prompts import PromptTemplate

prompt = PromptTemplate.from_template("请用{style}风格介绍{topic}")

print(prompt.format(style="通俗", topic="向量数据库"))
result = prompt.invoke({"style": "通俗", "topic": "向量数据库"})
```

`format()` 返回字符串，`invoke()` 返回 PromptValue，更适合接入链。

### 2. ChatPromptTemplate

`ChatPromptTemplate` 适合聊天模型。

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "你是一个 Python 老师。"),
        ("human", "请解释：{question}"),
    ]
)

messages = prompt.invoke({"question": "什么是列表推导式？"})
response = model.invoke(messages)
```

也可以使用 `from_template()` 快速创建：

```python
prompt = ChatPromptTemplate.from_template("请回答问题：{question}")
```

### 3. MessagesPlaceholder

`MessagesPlaceholder` 用于把历史消息插入模板。

```python
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder

prompt = ChatPromptTemplate.from_messages(
    [
        ("system", "你是一个有帮助的助手。"),
        MessagesPlaceholder(variable_name="history"),
        ("human", "{question}"),
    ]
)
```

适合多轮对话、带记忆的链。

### 4. FewShotPromptTemplate

Few-shot 模板用于在提示词中放入示例。

```python
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate

example_prompt = PromptTemplate.from_template("输入：{input}\n输出：{output}")

prompt = FewShotPromptTemplate(
    examples=[
        {"input": "质量很好", "output": "正面"},
        {"input": "物流太慢", "output": "负面"},
    ],
    example_prompt=example_prompt,
    suffix="输入：{text}\n输出：",
    input_variables=["text"],
)
```

### 5. 输出解析器 Output Parser

模型输出默认是消息对象或文本。输出解析器用于把结果转换成需要的格式。

```python
from langchain_core.output_parsers import StrOutputParser

chain = prompt | model | StrOutputParser()
answer = chain.invoke({"question": "什么是 RAG？"})
print(answer)
```

如果需要 JSON 或结构化对象，可以使用结构化输出或对应解析器。

## 九、LCEL、Runnable 与链式调用

### 1. LCEL 管道

LCEL 使用 `|` 把多个组件串起来。

```python
from langchain_core.output_parsers import StrOutputParser

chain = prompt | model | StrOutputParser()
answer = chain.invoke({"question": "什么是 LangChain？"})
```

数据流：

```text
输入 -> Prompt -> Model -> OutputParser -> 输出
```

### 2. Runnable 是什么

Runnable 是 LangChain 中很多组件的统一接口。常见方法：

| 方法 | 作用 |
| --- | --- |
| `invoke()` | 单次调用 |
| `batch()` | 批量调用 |
| `stream()` | 流式输出 |
| `ainvoke()` | 异步调用 |

```python
result = chain.invoke({"question": "你好"})
results = chain.batch([{"question": "A"}, {"question": "B"}])
```

流式输出：

```python
for chunk in chain.stream({"question": "介绍 Python"}):
    print(chunk, end="")
```

### 3. RunnableLambda

`RunnableLambda` 可以把普通 Python 函数包装进链。

```python
from langchain_core.runnables import RunnableLambda


def add_prefix(text: str) -> str:
    return "处理后：" + text

chain = RunnableLambda(add_prefix) | model
```

用于调试中间结果：

```python
def debug_print(value):
    print("当前中间结果：", value)
    return value

chain = prompt | RunnableLambda(debug_print) | model | StrOutputParser()
```

调试函数的关键是返回原值，不要破坏后续链需要的数据结构。

### 4. RunnablePassthrough

`RunnablePassthrough` 会把输入原样传递下去，RAG 中常用于保留用户原始问题。

```python
from langchain_core.runnables import RunnablePassthrough

rag_chain = (
    {
        "context": retriever | format_docs,
        "question": RunnablePassthrough(),
    }
    | prompt
    | model
    | StrOutputParser()
)
```

输入问题会分成两路：一路检索上下文，一路作为 `question` 保留。

### 5. 函数直接入链

简单函数有时可以直接参与 LCEL 组合。

```python
def format_docs(docs):
    return "\n\n".join(doc.page_content for doc in docs)

chain = retriever | format_docs | prompt | model | StrOutputParser()
```

如果需要更明确的 Runnable 行为，可以使用 `RunnableLambda`。

## 十、工具调用与 Agent

### 1. Tool 工具

工具就是模型可以调用的外部函数，例如查询天气、搜索数据库、调用业务接口。

普通函数示例：

```python
def add(a: int, b: int) -> int:
    """计算两个整数之和。"""
    return a + b
```

使用 `@tool`：

```python
from langchain_core.tools import tool

@tool
def get_weather(city: str) -> str:
    """查询城市天气。"""
    return f"{city} 今天晴。"
```

工具说明要写清楚，因为模型会根据名称、参数和 docstring 判断什么时候调用。

### 2. 手动执行工具

```python
result = get_weather.invoke({"city": "上海"})
print(result)
```

工具调用的关键：

- 参数类型要明确。
- 返回值尽量简单、结构清晰。
- 工具内部要处理异常。
- 不要让工具执行危险操作，尤其是删除、支付、数据库写入等。

### 3. Agent 智能体

Agent 会让模型根据任务自行选择工具、决定步骤并生成最终回答。

```python
from langchain.agents import create_agent

agent = create_agent(
    model=model,
    tools=[get_weather],
    system_prompt="你是一个可以调用工具的助手。",
)

result = agent.invoke(
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]}
)
```

### 4. system_prompt

`system_prompt` 用于设置 Agent 行为边界。

```text
你是一个客服助手。回答必须简洁。如果需要实时信息，必须调用工具；如果工具没有结果，请说明无法确认。
```

好的系统提示词能减少编造、约束工具使用方式。

### 5. Agent 多轮对话与状态

Agent 输入通常是 `messages`，多轮对话需要把历史消息传进去。

```python
messages = [
    {"role": "user", "content": "我叫小明"},
    {"role": "assistant", "content": "你好，小明。"},
    {"role": "user", "content": "我叫什么？"},
]

result = agent.invoke({"messages": messages})
```

如果没有传历史消息，模型就不知道前文。

### 6. Runtime Context 与结构化输出

Runtime Context 可用于把运行时信息传给工具或 Agent，例如用户 ID、权限、请求来源等。

结构化输出用于让模型按固定格式返回结果，例如 Pydantic 模型、JSON 字段等。适合分类、抽取、表单生成等场景。

## 十一、记忆与聊天历史

### 1. 临时记忆

`InMemoryChatMessageHistory` 适合学习和演示，数据只存在内存中，程序重启就丢失。

```python
from langchain_core.chat_history import InMemoryChatMessageHistory

history = InMemoryChatMessageHistory()
history.add_user_message("你好")
history.add_ai_message("你好，有什么可以帮你？")

print(history.messages)
```

### 2. RunnableWithMessageHistory

`RunnableWithMessageHistory` 可以给链增加历史对话能力。

```python
from langchain_core.runnables.history import RunnableWithMessageHistory

store = {}


def get_session_history(session_id: str):
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]

chain_with_history = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="question",
    history_messages_key="history",
)

result = chain_with_history.invoke(
    {"question": "我叫小明"},
    config={"configurable": {"session_id": "user-1"}},
)
```

核心是用 `session_id` 区分不同会话。

### 3. 长期会话记忆

长期记忆可以保存到文件、Redis、数据库或其他持久化存储。学习阶段可以用文件保存。

```python
import json
from pathlib import Path

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, messages_from_dict, message_to_dict


class FileChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, storage_path: str, session_id: str):
        self.storage_path = Path(storage_path)
        self.session_id = session_id

    @property
    def file_path(self) -> Path:
        return self.storage_path / f"{self.session_id}.json"

    @property
    def messages(self) -> list[BaseMessage]:
        if not self.file_path.exists():
            return []
        data = json.loads(self.file_path.read_text(encoding="utf-8"))
        return messages_from_dict(data)

    def add_messages(self, messages: list[BaseMessage]) -> None:
        all_messages = self.messages + messages
        data = [message_to_dict(message) for message in all_messages]
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text("[]", encoding="utf-8")
```

生产环境注意：

- 历史记录不能无限增长，需要窗口截断、摘要压缩或长期/短期记忆分层。
- 历史记录可能包含隐私数据，要考虑权限、加密、脱敏和清理策略。
- 多机器或高并发场景应使用 Redis、数据库或专门的会话存储。

## 十二、RAG 核心概念

### 1. RAG 解决什么问题

RAG 是 Retrieval-Augmented Generation，检索增强生成。

它解决的问题是：模型本身不知道私有知识、最新知识或业务资料，但可以先从知识库检索相关内容，再基于检索结果回答。

```text
用户问题 -> 检索相关资料 -> 把资料放进 Prompt -> 模型生成答案
```

RAG 适合：

- 企业知识库问答。
- 商品客服问答。
- 课程资料问答。
- 文档助手。
- 法规、制度、手册查询。

### 2. RAG 与微调的区别

| 对比项 | RAG | 微调 |
| --- | --- | --- |
| 主要目的 | 接入外部知识 | 改变模型行为或风格 |
| 知识更新 | 更新知识库即可 | 通常需要重新训练 |
| 可追溯性 | 可返回来源 | 较难追溯 |
| 成本 | 相对低 | 相对高 |
| 适合场景 | 知识问答、文档问答 | 固定任务风格、特定格式、领域表达 |

### 3. RAG 两条主线

离线流程，也叫建库流程：

```text
本地知识文件 -> 文档加载 -> 文本切分 -> Embedding 向量化 -> 写入向量数据库
```

在线流程，也叫问答流程：

```text
用户问题 -> 问题向量化 -> 向量匹配 -> 取回 Top-k 文档 -> 组装 Prompt -> 调用 LLM -> 生成答案
```

### 4. RAG 常见参数

| 参数 | 作用 | 建议 |
| --- | --- | --- |
| `chunk_size` | 每个文本块大小 | 太小容易缺上下文，太大检索不准 |
| `chunk_overlap` | 相邻文本块重叠 | 保留跨段信息，别过大 |
| `k` | 返回多少条检索结果 | 常见 3 到 8 |
| `temperature` | 模型随机性 | 知识问答通常设低 |
| `score_threshold` | 相似度阈值 | 用于过滤低相关结果 |

## 十三、文档加载与文本切分

### 1. Document 对象

LangChain 文档加载器通常返回 `Document` 对象。

| 字段 | 说明 |
| --- | --- |
| `page_content` | 文档正文内容 |
| `metadata` | 元数据，例如来源、页码、行号、业务字段 |

```python
from langchain_core.documents import Document

doc = Document(
    page_content="Python 是一种简单易学的编程语言。",
    metadata={"source": "python_notes.txt", "page": 1},
)
```

`metadata` 可用于展示答案来源、权限过滤、排查检索结果和按分类筛选知识。

### 2. Document Loaders

文档加载器负责把不同格式的数据读取成 `Document` 对象。

| 方法 | 作用 |
| --- | --- |
| `load()` | 一次性加载全部文档，返回 `list[Document]` |
| `lazy_load()` | 延迟加载，逐个返回文档，适合大文件 |

### 3. CSVLoader

`CSVLoader` 用于加载 CSV 文件。每一行通常会被转换成一个 `Document`。

```python
from langchain_community.document_loaders.csv_loader import CSVLoader

loader = CSVLoader(
    file_path="./data/info.csv",
    encoding="utf-8",
    source_column="source",
)

documents = loader.load()
```

自定义 CSV 参数：

```python
loader = CSVLoader(
    file_path="./data/users.csv",
    encoding="utf-8",
    csv_args={
        "delimiter": ",",
        "quotechar": '"',
        "fieldnames": ["name", "age", "gender"],
    },
)
```

如果 CSV 文件本身有表头，不要随便设置 `fieldnames`，否则第一行表头可能会被当成普通数据。

### 4. JSONLoader

`JSONLoader` 用于把 JSON 或 JSON Lines 数据加载成 `Document`。它依赖 `jq` 语法抽取字段。

常见 jq 规则：

| jq 写法 | 含义 |
| --- | --- |
| `.` | 整个 JSON 根对象 |
| `.name` | 取根对象中的 `name` 字段 |
| `.hobby[1]` | 取数组第二个元素 |
| `.other.addr` | 取嵌套字段 |
| `.[]` | 遍历数组中的每个对象 |
| `.[].name` | 取数组中每个对象的 `name` |

```python
from langchain_community.document_loaders import JSONLoader

loader = JSONLoader(
    file_path="./data/user.json",
    jq_schema=".",
    text_content=False,
)

documents = loader.load()
```

JSON Lines 每一行都是一个独立 JSON 对象：

```python
loader = JSONLoader(
    file_path="./data/users.jsonl",
    jq_schema=".",
    text_content=False,
    json_lines=True,
)
```

### 5. TextLoader

```python
from langchain_community.document_loaders import TextLoader

loader = TextLoader("./data/python_notes.txt", encoding="utf-8")
docs = loader.load()
```

一般会把整个文本文件内容放入一个 `Document`，后续通常要切分。

### 6. PyPDFLoader

`PyPDFLoader` 用于读取 PDF 文件，依赖 `pypdf`。

```python
from langchain_community.document_loaders import PyPDFLoader

loader = PyPDFLoader(
    file_path="./data/manual.pdf",
    mode="page",
    password=None,
)

docs = loader.load()
```

常见模式：

| 参数 | 说明 |
| --- | --- |
| `mode="page"` | 按页生成多个 Document |
| `mode="single"` | 整个 PDF 合成一个 Document |
| `password` | 加密 PDF 的密码 |

扫描版 PDF 可能需要 OCR，表格、分栏、页眉页脚也可能影响文本质量。

### 7. RecursiveCharacterTextSplitter

文档加载后通常要切成多个 chunk，便于向量检索和控制上下文长度。

```python
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

loader = TextLoader("./data/python_notes.txt", encoding="utf-8")
docs = loader.load()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""],
    length_function=len,
)

split_docs = splitter.split_documents(docs)
```

核心参数：

| 参数 | 作用 |
| --- | --- |
| `chunk_size` | 每个 chunk 的最大长度 |
| `chunk_overlap` | 相邻 chunk 的重叠长度 |
| `separators` | 分隔符优先级 |
| `length_function` | 长度计算函数 |

中文文档可以把 `。`、`！`、`？`、`，` 放进分隔符，切分后要抽样检查语义是否完整。

## 十四、向量、Embedding 与向量存储

### 1. 向量与 Embedding

Embedding 是把文本转换成数字向量的过程。语义相近的文本，向量距离通常更近。

```text
"Python 入门" -> [0.12, -0.08, 0.33, ...]
```

在 RAG 中：

- 离线阶段：文档 -> Embedding -> 存入向量库。
- 在线阶段：问题 -> Embedding -> 向量库相似度搜索。

### 2. 余弦相似度

余弦相似度关注向量方向是否接近，常用于判断语义相似。

```python
import math


def cosine_similarity(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    return dot / (norm_a * norm_b)
```

### 3. LangChain Embeddings

```python
# 示例：根据项目实际供应商替换
# from langchain_openai import OpenAIEmbeddings
# embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

vector = embeddings.embed_query("Python 是不是简单易学？")
vectors = embeddings.embed_documents(["Python 入门", "LangChain RAG"])
```

### 4. Vector Stores

向量存储负责保存文档向量，并执行相似度搜索。

```text
文档 -> Embedding -> 向量 -> VectorStore
问题 -> Embedding -> 查询向量 -> Similarity Search -> Top-k 文档
```

常见能力：

| 方法 | 作用 |
| --- | --- |
| `add_documents()` | 添加文档到向量存储 |
| `add_texts()` | 直接添加文本 |
| `delete()` | 删除文档 |
| `similarity_search()` | 相似度搜索 |
| `as_retriever()` | 转为检索器 |

### 5. InMemoryVectorStore

内存向量存储适合学习和临时演示。

```python
from langchain_core.vectorstores import InMemoryVectorStore

vector_store = InMemoryVectorStore(embedding=embeddings)

ids = vector_store.add_documents(
    documents=split_docs,
    ids=[f"doc-{i}" for i in range(len(split_docs))],
)

results = vector_store.similarity_search("Python 是不是简单易学？", k=3)
```

数据只在内存中，程序结束就丢失，不适合生产知识库。

### 6. Chroma 向量存储

Chroma 是常见的本地/外部向量数据库选择之一。

```python
from langchain_chroma import Chroma

vector_store = Chroma(
    collection_name="example_collection",
    embedding_function=embeddings,
    persist_directory="./chroma_langchain_db",
)

vector_store.add_documents(
    documents=split_docs,
    ids=[f"doc-{i}" for i in range(len(split_docs))],
)

results = vector_store.similarity_search("怎么学习 Python？", k=3)
```

注意：

- `persist_directory` 表示本地持久化目录。
- 不同 collection 可以隔离不同知识库。
- 真实项目要设计文档 ID、更新策略、删除策略和元数据过滤。

## 十五、RAG 链与项目实战

### 1. RAG Prompt 模板

```python
from langchain_core.prompts import ChatPromptTemplate

prompt = ChatPromptTemplate.from_template(
    """你是一个严谨的知识库助手。
请只根据【参考资料】回答用户问题。
如果参考资料中没有答案，请说“资料中没有相关信息”，不要编造。

【参考资料】
{context}

【用户问题】
{question}
"""
)
```

### 2. 手动检索并回答

```python
from langchain_core.output_parsers import StrOutputParser

question = "这件衣服适合冬天穿吗？"
retrieved_docs = vector_store.similarity_search(question, k=3)

context = "\n\n".join(
    f"来源：{doc.metadata.get('source', '未知')}\n内容：{doc.page_content}"
    for doc in retrieved_docs
)

chain = prompt | model | StrOutputParser()
answer = chain.invoke({"context": context, "question": question})
```

### 3. Retriever + RunnablePassthrough

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough


def format_docs(docs):
    return "\n\n".join(
        f"来源：{doc.metadata.get('source', '未知')}\n内容：{doc.page_content}"
        for doc in docs
    )

retriever = vector_store.as_retriever(search_kwargs={"k": 3})

rag_chain = (
    {
        "context": retriever | format_docs,
        "question": RunnablePassthrough(),
    }
    | prompt
    | model
    | StrOutputParser()
)

answer = rag_chain.invoke("这款商品有什么尺码？")
```

### 4. 商品知识库项目需求

以“某东商品衣服”为例，可以用本地商品资料构建知识库。

项目目标：

- 使用本地文件构建知识库。
- 用户可以自由更新本地知识文件。
- 用户提问时，答案尽量基于本地知识生成。
- 模型不知道或资料中没有的内容，要明确说明，不要编造。
- 最好能返回答案来源，便于追溯。

### 5. 商品 CSV 数据设计

```csv
source,content
商品A,商品A是一件加厚羽绒服，适合秋冬季节，尺码包含M、L、XL。
商品B,商品B是一件轻薄防晒衣，适合春夏通勤和户外运动。
退换货规则,商品签收后7天内可申请无理由退换，吊牌剪掉后不支持退换。
```

使用 `source_column` 把来源写入 `metadata`：

```python
loader = CSVLoader(
    file_path="./data/products.csv",
    encoding="utf-8",
    source_column="source",
)

documents = loader.load()
```

### 6. 离线建库代码骨架

```python
from langchain_chroma import Chroma
from langchain_community.document_loaders.csv_loader import CSVLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

loader = CSVLoader(
    file_path="./data/products.csv",
    encoding="utf-8",
    source_column="source",
)
docs = loader.load()

splitter = RecursiveCharacterTextSplitter(
    chunk_size=500,
    chunk_overlap=50,
    separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""],
)
split_docs = splitter.split_documents(docs)

vector_store = Chroma(
    collection_name="product_knowledge",
    embedding_function=embeddings,
    persist_directory="./chroma_product_db",
)

ids = [f"product-doc-{i}" for i in range(len(split_docs))]
vector_store.add_documents(documents=split_docs, ids=ids)
```

### 7. 返回答案来源

```python
question = "商品A支持退换货吗？"
docs = retriever.invoke(question)

context = format_docs(docs)
answer = chain.invoke({"context": context, "question": question})

sources = []
for doc in docs:
    source = doc.metadata.get("source")
    if source and source not in sources:
        sources.append(source)

result = {
    "answer": answer,
    "sources": sources,
}
```

### 8. 知识更新、删除与重建

| 场景 | 推荐做法 |
| --- | --- |
| 少量文档新增 | 调用 `add_documents()` 添加新 chunk |
| 单个商品更新 | 先删除旧商品对应 chunk，再添加新 chunk |
| 大批量资料变化 | 重新构建 collection 或新建 collection 后切换 |
| 需要灰度发布 | 新旧 collection 并存，验证后切流 |

删除时需要稳定 ID：

```python
vector_store.delete(ids=["product-A-001", "product-A-002"])
```

真实项目中建议使用业务相关 ID，例如：

```text
product_id + chunk_index
```

### 9. RAG 调试与排查

| 问题 | 可能原因 | 处理方式 |
| --- | --- | --- |
| 检索不到正确内容 | chunk 太大或太小、Embedding 效果差、问题表达不一致 | 调整切分参数，换 Embedding，增加同义词内容 |
| 答案编造 | Prompt 没有限制，检索资料不足 | 加强“不知道就说明”的约束，返回来源 |
| 回答引用错商品 | 来源字段缺失或 chunk 混杂多个商品 | 每个 chunk 保持单一主题，保留商品 ID |
| 更新后仍答旧内容 | 旧向量未删除或 collection 用错 | 检查 ID、collection、persist_directory |
| 速度慢 | Top-k 太大、文档太多、模型慢 | 控制 `k`，使用更快向量库，做缓存 |

建议打印：

```python
print("用户问题：", question)
print("检索结果：", [doc.metadata for doc in retrieved_docs])
print("Prompt上下文：", context[:1000])
```

## 十六、Streamlit + LangChain 常见模式

Streamlit 适合快速做大模型应用页面。

常见结构：

```python
import streamlit as st

st.title("知识库问答")

question = st.chat_input("请输入问题")
if question:
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        answer = rag_chain.invoke(question)
        st.write(answer)
```

常见注意点：

- 用 `st.session_state` 保存页面状态和聊天记录。
- 模型调用要加 loading 提示。
- API Key 不要写死在页面代码里。
- RAG 应用最好展示引用来源。

## 十七、常见错误与排查

### 1. 环境变量没加载

表现：API Key 找不到。

处理：检查 `.env`、环境变量名、启动目录和加载逻辑。

### 2. 工具不被调用

可能原因：工具名称不清晰、docstring 不明确、Prompt 没要求必须调用工具。

处理：改清楚工具说明，并在系统提示词中规定使用条件。

### 3. Agent 编造结果

处理：

- 要求必须基于工具结果回答。
- 工具无结果时明确说无法确认。
- 降低 `temperature`。
- 返回工具调用过程或来源。

### 4. 多轮对话丢上下文

可能原因：没有传历史消息，或 `session_id` 不一致。

处理：检查 `MessagesPlaceholder`、`RunnableWithMessageHistory` 和调用时的 `config`。

### 5. 中文输出乱码

处理：

- 文件读写指定 `encoding="utf-8"`。
- JSON 使用 `ensure_ascii=False`。
- 终端、编辑器、系统编码保持一致。

### 6. RAG 答案不准

优先排查顺序：

1. Loader 是否正确读到内容。
2. chunk 是否切得合理。
3. Embedding 是否适合中文或当前领域。
4. 检索 Top-k 是否拿到了正确资料。
5. Prompt 是否明确限制只能基于资料回答。

## 十八、学习路线与小抄

### 1. Python 阶段

建议顺序：

1. 变量、类型、字符串。
2. 条件判断、循环、函数。
3. 列表、字典、元组、集合。
4. 文件、JSON、异常处理。
5. 类型注解、模块化、dataclass。

### 2. LangChain 阶段

建议顺序：

1. 模型调用与消息格式。
2. Prompt 模板与输出解析。
3. LCEL、Runnable、链式调用。
4. 工具调用和 Agent。
5. 聊天历史和记忆。
6. Document、Loader、TextSplitter。
7. Embedding、VectorStore、Retriever。
8. RAG 项目实战。

### 3. 常用小抄

Python：

```python
# 列表推导式
[x * x for x in range(10) if x % 2 == 0]

# 字典遍历
for key, value in data.items():
    print(key, value)

# JSON
json.loads(text)
json.dumps(data, ensure_ascii=False, indent=2)

# 文件
Path("demo.txt").read_text(encoding="utf-8")
```

LangChain：

```python
# 基础链
chain = prompt | model | StrOutputParser()

# RAG 链
rag_chain = (
    {"context": retriever | format_docs, "question": RunnablePassthrough()}
    | prompt
    | model
    | StrOutputParser()
)

# 带历史
chain_with_history = RunnableWithMessageHistory(
    chain,
    get_session_history,
    input_messages_key="question",
    history_messages_key="history",
)
```

## 十九、官方参考

LangChain 版本迭代较快，遇到 API 差异时优先查看官方文档：

- LangChain Python Overview: <https://docs.langchain.com/oss/python/langchain/overview>
- LangChain RAG: <https://docs.langchain.com/oss/python/langchain/rag>
- LangChain Document Loaders: <https://docs.langchain.com/oss/python/integrations/document_loaders/>
- LangChain Text Splitters: <https://docs.langchain.com/oss/python/integrations/splitters/index>
- LangChain Vector Stores: <https://docs.langchain.com/oss/python/integrations/vectorstores/>
- LangChain Chroma: <https://docs.langchain.com/oss/python/integrations/vectorstores/chroma>
- LangChain Models: <https://docs.langchain.com/oss/python/langchain-models>
- LangChain Embeddings: <https://docs.langchain.com/oss/python/integrations/embeddings>
- ChatPromptTemplate API: <https://api.python.langchain.com/en/latest/core/prompts/langchain_core.prompts.chat.ChatPromptTemplate.html>
- RunnableLambda API: <https://api.python.langchain.com/en/latest/core/runnables/langchain_core.runnables.base.RunnableLambda.html>
- RunnablePassthrough Reference: <https://reference.langchain.com/python/langchain-core/runnables/passthrough/RunnablePassthrough/>
- RunnableWithMessageHistory API: <https://api.python.langchain.com/en/latest/runnables/langchain_core.runnables.history.RunnableWithMessageHistory.html>
- Agents: <https://docs.langchain.com/oss/python/langchain/agents>
- Tools: <https://docs.langchain.com/oss/python/langchain/tools>
- Structured Output: <https://docs.langchain.com/oss/python/langchain/structured-output>
- Ollama Docs: <https://docs.ollama.com/>

# Python 与 LangChain 常用知识点整理

本文档用于快速复习 Python 基础语法、AI 应用开发基础，以及 LangChain 中常用的模型、提示词、链、工具、智能体、记忆和 RAG 知识点。内容按功能重新整理：相同主题集中在一起，先 Python，后大模型，再 LangChain，最后 RAG 项目实战。

整理原则：

- 按功能模块组织，而不是按课程截图出现顺序组织。
- 功能相同的内容合并到同一章，例如 Prompt、RAG、向量库、记忆等。
- 保留学习笔记需要的细节：概念说明、常用 API、示例代码、注意点和排查方法。
- LangChain 版本变化较快，示例以当前常见写法为主，遇到导入路径差异时优先查看官方文档。

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

常见布尔判断：

```python
if name:
    print("name 不是空字符串")

if items:
    print("列表不为空")

if value is None:
    print("value 是空值")
```

Python 中这些值通常会被当作 `False`：

| 值 | 说明 |
| --- | --- |
| `False` | 布尔假 |
| `None` | 空值 |
| `0` / `0.0` | 数字零 |
| `""` | 空字符串 |
| `[]` / `{}` / `set()` / `()` | 空容器 |

本阶段小结：

- 变量保存的是对象引用，变量名只是指向数据的名字。
- 字符串是最常用的数据类型之一，建议熟练掌握 f-string。
- `input()` 的结果永远是字符串，需要手动转换。
- 判断空值时，`is None` 比 `== None` 更推荐。

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

循环常见模式：

```python
# 遍历列表
for item in items:
    print(item)

# 遍历下标
for i in range(len(items)):
    print(i, items[i])

# 同时获取下标和值，更推荐
for i, item in enumerate(items):
    print(i, item)
```

嵌套循环：

```python
for i in range(3):
    for j in range(2):
        print(i, j)
```

注意：嵌套循环会增加执行次数。外层循环 3 次、内层循环 2 次，总共执行 6 次。

本阶段小结：

- `if` 解决分支选择。
- `for` 适合遍历已知序列。
- `while` 适合“不确定循环次数，但知道停止条件”的场景。
- `break` 结束循环，`continue` 跳过本轮。
- `range()` 常和 `for` 配合生成数字序列。

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

容器通用操作：

```python
len(items)          # 长度
"Python" in items   # 是否包含
for item in items:  # 遍历
    print(item)
```

排序与反转：

```python
nums = [3, 1, 2]

print(sorted(nums))  # 返回新列表
nums.sort()          # 原地排序
nums.reverse()       # 原地反转
```

浅拷贝：

```python
a = [1, 2, 3]
b = a.copy()
b.append(4)

print(a)  # [1, 2, 3]
print(b)  # [1, 2, 3, 4]
```

本阶段小结：

- 列表适合保存一组有顺序的数据。
- 字典适合保存对象属性、接口响应、配置等结构化数据。
- 元组常用于固定结构和函数多返回值。
- 集合适合去重和集合运算。
- 切片、推导式和字典遍历是 Python 高频写法。

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

可变默认参数要避免：

```python
# 不推荐
def add_item_bad(item, items=[]):
    items.append(item)
    return items

# 推荐
def add_item(item, items=None):
    if items is None:
        items = []
    items.append(item)
    return items
```

函数返回多个值时，本质上返回的是元组：

```python
def get_user():
    return "Alice", 18

name, age = get_user()
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

常见异常：

| 异常 | 常见原因 |
| --- | --- |
| `ValueError` | 类型转换失败，例如 `int("abc")` |
| `KeyError` | 字典 key 不存在 |
| `IndexError` | 列表下标越界 |
| `FileNotFoundError` | 文件不存在 |
| `TypeError` | 类型不匹配 |

本阶段小结：

- 函数用于封装复用逻辑，参数和返回值要尽量清晰。
- 类型注解不是强制运行检查，但能显著提升可读性。
- `dataclass` 适合保存结构化数据。
- 模块导入能让代码拆分得更清楚。
- 异常处理用于处理可预期失败，不要用裸 `except` 吞掉所有错误。

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

JSON 和 Python 类型对应关系：

| JSON | Python |
| --- | --- |
| object | `dict` |
| array | `list` |
| string | `str` |
| number | `int` / `float` |
| true / false | `True` / `False` |
| null | `None` |

常见坑：

- `json.dumps()` 默认会把中文转义，保存中文时加 `ensure_ascii=False`。
- JSON 的 key 必须是字符串。
- JSON 文件中不能写 Python 的 `True`、`False`、`None`，要写 `true`、`false`、`null`。

本阶段小结：

- 路径处理优先用 `pathlib.Path`。
- 密钥、Token、模型配置不要硬编码。
- JSON 是大模型应用里非常常见的数据交换格式。
- 文件读写要指定 `encoding="utf-8"`。

## 六、AI 应用与大模型基础

### 1. 大模型应用是什么

大模型应用不是“只把问题丢给模型”，而是把传统程序的确定性控制和大模型的推理、分析、生成能力结合起来。可以把它理解为一种 Hybrid AI 应用：

```text
传统程序：负责输入校验、权限、业务流程、数据读写、合规检查
大模型：负责理解自然语言、推理、生成、总结、分类、抽取
```

常见调用方式是：传统应用通过 HTTP API 调用大模型服务，大模型返回文本、结构化数据或工具调用请求，应用再继续做业务处理。

典型流程：

```text
用户提问
  -> 传统应用接收输入
  -> 预处理、权限校验、合规检查
  -> 通过 HTTP API 调用大模型
  -> 大模型理解、推理、生成
  -> 应用解析结果、再次做合规检查
  -> 返回给用户
```

一个容易混淆的概念：

| 名称 | 含义 |
| --- | --- |
| GPT | 底层语言模型，负责理解和生成语言 |
| ChatGPT | 基于 GPT 等模型构建的聊天产品或应用 |

所以我们用 LangChain、FastAPI、Streamlit 等做的应用，本质上也可以理解为“基于大模型能力封装出来的产品”。

### 2. 大模型部署方案

常见部署方式：

| 方式 | 特点 | 适合场景 |
| --- | --- | --- |
| 云端 API | 接入简单，效果稳定 | 快速开发、生产应用 |
| 本地模型 | 数据可控，无需外部 API | 学习、内网、隐私场景 |
| 私有化部署 | 可控性强，成本和运维更高 | 企业内部系统 |

### 3. Ollama 本地模型

Ollama 可用于本地运行模型。

常用命令示例：

```powershell
ollama pull qwen2.5
ollama run qwen2.5
ollama list
```

在 LangChain 中调用 Ollama 时，通常使用对应集成包或 `init_chat_model` 统一初始化。

### 4. HTTP API 与大模型交互

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

### 5. 提示词工程

提示词工程的目标是让模型更稳定地完成任务。

常见原则：

- 明确角色：告诉模型扮演谁。
- 明确任务：说明要完成什么。
- 明确约束：说明不能做什么。
- 明确输出格式：例如 JSON、表格、列表。
- 提供示例：减少模型理解偏差。

### 6. Zero-shot 与 Few-shot

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

### 7. 提示词常见结构

一个稳定的提示词通常包含这些部分：

```text
角色：你是谁
任务：你要做什么
背景：你可以参考什么信息
约束：不能做什么
输出格式：必须怎么输出
示例：给出 1 到 3 个参考样例
```

示例：

```text
你是一个 Python 教学助手。
请用初学者能理解的方式解释下面的概念。
要求：
1. 先给一句话解释
2. 再给一个代码示例
3. 不要使用太多术语

概念：列表推导式
```

### 8. 大模型应用常见流程

```text
用户输入 -> Prompt 组装 -> 模型调用 -> 输出解析 -> 业务处理 -> 返回结果
```

如果接入外部知识或工具，流程会变成：

```text
用户输入 -> 检索/工具调用 -> Prompt 组装 -> 模型调用 -> 解析结果 -> 返回
```

本阶段小结：

- 大模型应用通常是“传统程序 + 大模型能力”的组合，不是完全交给模型自由发挥。
- 云端 API 接入快，本地模型数据更可控。
- HTTP API 调用要考虑超时、重试和异常处理。
- Prompt 要明确角色、任务、约束和输出格式。
- Few-shot 可以让模型更容易模仿你想要的输出。
- RAG、Agent、工具调用都建立在“模型调用 + 上下文组织”的基础上。

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

# init_chat_model 用统一写法创建聊天模型。
# 如果你用的是 DeepSeek，可以按项目实际配置换成 ChatDeepSeek 或兼容接口。
model = init_chat_model(
    # provider:model 的写法表示使用 OpenAI 的 gpt-4o-mini。
    "openai:gpt-4o-mini",
    # temperature 越低，回答越稳定，适合教学、RAG 和结构化输出。
    temperature=0,
)

# invoke 是最常用的同步调用方式。
response = model.invoke("你好，请用一句话介绍 LangChain")

# 聊天模型返回的是消息对象，正文一般在 content 字段里。
print(response.content)
```

这段代码可以按步骤理解：

1. `init_chat_model(...)`：初始化一个聊天模型。
2. `"openai:gpt-4o-mini"`：指定模型供应商和模型名。
3. `temperature=0`：降低随机性，让结果更可控。
4. `model.invoke(...)`：把用户输入发送给模型。
5. `response.content`：读取模型回复文本。

常见参数：

| 参数 | 作用 |
| --- | --- |
| `model` | 模型名称 |
| `temperature` | 随机性，越低越稳定 |
| `max_tokens` | 最大输出长度 |
| `timeout` | 请求超时 |

### 4. 消息格式

聊天模型通常接收消息列表。在 LangChain 中，发给模型和模型返回的聊天消息通常会被包装成 `BaseMessage` 及其子类，而不是单纯的字符串。

```python
from langchain_core.messages import HumanMessage, SystemMessage

# messages 是聊天模型最常见的输入格式。
messages = [
    # SystemMessage 用来约束模型身份、规则和回答边界。
    SystemMessage(content="你是一个严谨的 Python 老师。"),
    # HumanMessage 表示用户真正提出的问题。
    HumanMessage(content="解释一下 list 和 tuple 的区别。"),
]

response = model.invoke(messages)
print(response.content)
```

这段代码可以按步骤理解：

1. `SystemMessage`：告诉模型“你是谁、要按什么规则回答”。
2. `HumanMessage`：用户输入。
3. `model.invoke(messages)`：把整组聊天消息交给模型。
4. `response.content`：取出最终自然语言回复。

常见消息类型：

| 类型 | 对应角色 | 说明 |
| --- | --- | --- |
| `SystemMessage` | system | 设置模型角色、背景、行为边界和任务规则 |
| `HumanMessage` | user | 用户输入的问题、指令或补充信息 |
| `AIMessage` | assistant | 模型回复，可能包含文本、工具调用、响应元数据 |
| `ToolMessage` | tool | 工具执行后的返回结果，通常传回给模型继续推理 |

也可以用字典形式传消息，LangChain 会在内部转换：

```python
messages = [
    # 字典形式也可以表达 system / user / assistant / tool 等角色。
    {"role": "system", "content": "你是一个严谨的 Python 老师。"},
    {"role": "user", "content": "解释一下 list 和 tuple 的区别。"},
]

response = model.invoke(messages)
```

理解消息对象很重要，因为后面的 `Agent`、`MessagesPlaceholder`、`RunnableWithMessageHistory` 都是在围绕消息列表组织上下文。

### 5. 模型类型选择

| 类型 | 作用 | 示例场景 |
| --- | --- | --- |
| Chat Model | 对话和文本生成 | 问答、客服、总结 |
| Embedding Model | 文本向量化 | RAG、相似度搜索 |
| Rerank Model | 检索结果重排 | 提升 RAG 命中质量 |
| Image / Multimodal Model | 图像理解或生成 | 图片问答、多模态应用 |

模型调用常见注意点：

- `temperature=0` 更稳定，适合知识问答、代码生成、结构化输出。
- `temperature` 较高时更发散，适合创意写作。
- 聊天模型返回的通常是消息对象，真正文本在 `.content` 中。
- 不同供应商的模型名称、鉴权环境变量、上下文长度不同。
- 生产项目要记录请求耗时、错误信息和模型返回状态，但不要把 API Key 写入日志。

本阶段小结：

- LangChain 把模型、Prompt、工具、检索器等统一成可组合组件。
- Chat Model 负责生成回答，Embedding Model 负责文本向量化。
- LangChain 的聊天上下文主要由 `BaseMessage` 子类组成。
- `SystemMessage` 用于设定角色和约束，`HumanMessage` 表示用户问题，`ToolMessage` 表示工具结果。
- 初始化模型时重点关注模型名、温度、超时和密钥配置。

## 八、Prompt 模板与输出解析

### 1. PromptTemplate

`PromptTemplate` 适合普通字符串模板。

```python
from langchain_core.prompts import PromptTemplate

# from_template 会把普通字符串变成可复用 Prompt 模板。
prompt = PromptTemplate.from_template("请用{style}风格介绍{topic}")

# format 返回普通字符串，适合快速查看模板渲染结果。
print(prompt.format(style="通俗", topic="向量数据库"))

# invoke 返回 PromptValue，更适合接到后面的 model / parser 链里。
result = prompt.invoke({"style": "通俗", "topic": "向量数据库"})
```

`format()` 返回字符串，`invoke()` 返回 PromptValue，更适合接入链。

### 2. ChatPromptTemplate

`ChatPromptTemplate` 适合聊天模型。

```python
from langchain_core.prompts import ChatPromptTemplate

# ChatPromptTemplate 生成的是一组聊天消息，不只是一个字符串。
prompt = ChatPromptTemplate.from_messages(
    [
        # system 消息固定角色和风格。
        ("system", "你是一个 Python 老师。"),
        # human 消息里的 {question} 会在 invoke 时被替换。
        ("human", "请解释：{question}"),
    ]
)

# 把变量 question 填入模板，得到 PromptValue / messages。
messages = prompt.invoke({"question": "什么是列表推导式？"})

# 再把格式化后的消息交给模型。
response = model.invoke(messages)
```

这段代码可以按步骤理解：

1. `ChatPromptTemplate.from_messages(...)`：创建聊天模板。
2. `("system", "...")`：定义系统消息。
3. `("human", "请解释：{question}")`：定义用户消息模板。
4. `prompt.invoke({...})`：把变量填进去。
5. `model.invoke(messages)`：让模型基于模板后的消息回答。

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
        # 这里会插入历史消息列表，例如 HumanMessage、AIMessage。
        MessagesPlaceholder(variable_name="history"),
        # 当前用户问题单独放在最后。
        ("human", "{question}"),
    ]
)
```

这段代码可以按步骤理解：

1. `MessagesPlaceholder("history")`：预留一个位置，用来插入多轮历史。
2. `history` 调用时必须传入消息列表。
3. 最新问题放在最后，模型通常会更重视靠后的当前任务。
4. 它常和 `RunnableWithMessageHistory` 或 Agent 记忆一起使用。

适合多轮对话、带记忆的链。

### 4. FewShotPromptTemplate

Few-shot 模板用于在提示词中放入示例。

```python
from langchain_core.prompts import FewShotPromptTemplate, PromptTemplate

# 单条示例的格式。
example_prompt = PromptTemplate.from_template("输入：{input}\n输出：{output}")

prompt = FewShotPromptTemplate(
    # examples 是给模型看的示范样本。
    examples=[
        {"input": "质量很好", "output": "正面"},
        {"input": "物流太慢", "output": "负面"},
    ],
    # 每条示例用 example_prompt 格式化。
    example_prompt=example_prompt,
    # suffix 是真实待处理输入的位置。
    suffix="输入：{text}\n输出：",
    # 调用 prompt 时必须提供 text。
    input_variables=["text"],
)
```

Few-shot 的重点不是“示例越多越好”，而是让示例和真实任务足够接近，模型能模仿你的判断逻辑和输出格式。

### 5. Prompt 工程常用结构

Prompt 会影响模型的角色、聊天背景、任务理解、输出格式和安全边界。稳定的 Prompt 通常包含下面几类信息：

| 组成 | 作用 | 示例 |
| --- | --- | --- |
| Identity | 指定模型身份和视角 | 你是一个资深 Python 教学助手 |
| Instructions | 说明任务和步骤 | 先解释概念，再给代码，再总结注意点 |
| Examples | 给出示例让模型模仿 | 输入 A 输出 B，输入 C 输出 D |
| Context | 提供背景资料或检索内容 | 以下是商品资料、用户历史、知识库片段 |
| Output Format | 约束输出格式 | 返回 JSON，字段包括 answer、reason |

Markdown 标题、列表、代码块能让提示词结构更清楚：

```text
# 角色
你是一个严谨的代码审查助手。

# 任务
检查下面代码是否存在 bug。

# 输出格式
- 问题：
- 原因：
- 修改建议：

# 代码
{code}
```

XML 风格标签适合明确分隔上下文，尤其是 RAG 或长文本任务：

```text
<context>
{retrieved_docs}
</context>

<question>
{question}
</question>

请只根据 <context> 中的信息回答。
```

Prompt 编写建议：

- 重要规则放在靠前位置，并写得具体。
- 输出要给字段名、格式、示例，减少模型自由发挥。
- 对不能做的事要明确，例如“没有依据时回答不知道”。
- 长上下文要用标签、标题或分隔符隔开，避免模型混淆。
- Few-shot 示例要覆盖常见边界情况，例如空值、格式错误、无法判断。

### 6. 输出解析器 Output Parser

模型输出默认是消息对象或文本。输出解析器用于把结果转换成需要的格式。

```python
from langchain_core.output_parsers import StrOutputParser

# LCEL 管道：Prompt 的输出进入 model，model 的输出再进入字符串解析器。
chain = prompt | model | StrOutputParser()

# invoke 的输入必须匹配 prompt 需要的变量。
answer = chain.invoke({"question": "什么是 RAG？"})
print(answer)
```

这段代码可以按步骤理解：

1. `prompt | model | StrOutputParser()`：把三个组件串成一条链。
2. `prompt`：负责把输入变量变成模型消息。
3. `model`：负责生成回复。
4. `StrOutputParser()`：把模型消息对象解析成普通字符串。
5. `chain.invoke(...)`：一次性执行整条链。

如果需要 JSON 或结构化对象，可以使用结构化输出或对应解析器。

### 7. Prompt 变量与格式化

Prompt 中的 `{变量名}` 必须在调用时传入。

```python
prompt = ChatPromptTemplate.from_template("请把{topic}解释给{audience}听")

value = prompt.invoke(
    {
        "topic": "RAG",
        "audience": "Python 初学者",
    }
)
```

如果变量名写错，会在格式化或调用时报错。

```python
# 模板中需要 topic，但调用时传了 question
prompt.invoke({"question": "RAG"})
```

### 8. 结构化输出思路

当你希望模型返回固定字段时，可以在提示词中明确 JSON 格式。

```python
prompt = ChatPromptTemplate.from_template(
    """请从文本中抽取商品信息，并返回 JSON。
字段包括：name、price、features。

文本：{text}
"""
)
```

这种方式简单，但模型可能返回多余文本、字段缺失或 JSON 不合法。适合学习和轻量脚本。

更可靠的做法是使用模型或 LangChain 提供的结构化输出能力，让返回结果符合 Pydantic 模型或 JSON Schema。

Pydantic 示例：

```python
from pydantic import BaseModel, Field


class ProductInfo(BaseModel):
    # Field(description=...) 会告诉模型每个字段的含义。
    name: str = Field(description="商品名称")
    price: float | None = Field(description="商品价格，如果没有则为 None")
    features: list[str] = Field(description="商品特点列表")


# with_structured_output 会让模型尽量按 ProductInfo 返回结构化对象。
structured_model = model.with_structured_output(ProductInfo)

result = structured_model.invoke("商品A售价199元，适合秋冬穿，保暖性好。")

# 结果可以像普通 Python 对象一样读取字段。
print(result.name)
print(result.features)
```

城市信息示例：

```python
from pydantic import BaseModel, Field


class CapitalInfo(BaseModel):
    name: str = Field(description="首都名称")
    location: str = Field(description="所在国家或地区")
    vibe: str = Field(description="城市气质或特点")
    economy: str = Field(description="经济特点")


structured_model = model.with_structured_output(CapitalInfo)
result = structured_model.invoke("请介绍一下法国首都巴黎。")

print(result.name)
print(result.location)
```

两种结构化方式对比：

| 方式 | 优点 | 风险 |
| --- | --- | --- |
| Prompt 中要求 JSON | 简单、通用、容易理解 | 可能输出不合法 JSON，需要额外解析和兜底 |
| Pydantic / JSON Schema | 字段约束更强，程序更好接 | 需要模型或供应商支持结构化输出能力 |

结构化输出适合：

- 信息抽取。
- 文本分类。
- 表单填写。
- 多字段分析报告。
- 后续要被程序继续处理的模型结果。

本阶段小结：

- `PromptTemplate` 偏普通文本，`ChatPromptTemplate` 偏聊天消息。
- `MessagesPlaceholder` 用于插入历史消息。
- Few-shot 用示例约束模型输出。
- 好的 Prompt 通常由身份、指令、示例、上下文和输出格式组成。
- Output Parser 用于把模型结果转换成字符串、JSON 或业务对象。
- Prompt 变量名要和调用参数保持一致。

## 九、LCEL、Runnable 与链式调用

### 1. LCEL 管道

LCEL 使用 `|` 把多个组件串起来。

```python
from langchain_core.output_parsers import StrOutputParser

# 这条链的数据流是：输入字典 -> prompt -> model -> 字符串解析器。
chain = prompt | model | StrOutputParser()

# question 会先填进 prompt，再交给模型回答。
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
# 单次调用，返回一个结果。
result = chain.invoke({"question": "你好"})

# 批量调用，输入是多个参数字典，返回多个结果。
results = chain.batch([{"question": "A"}, {"question": "B"}])
```

流式输出：

```python
# stream 会边生成边返回片段，适合做打字机效果。
for chunk in chain.stream({"question": "介绍 Python"}):
    print(chunk, end="")
```

### 3. RunnableLambda

`RunnableLambda` 可以把普通 Python 函数包装进链。

```python
from langchain_core.runnables import RunnableLambda


def add_prefix(text: str) -> str:
    # 普通 Python 函数：输入字符串，返回处理后的字符串。
    return "处理后：" + text

# RunnableLambda 把普通函数包装成可以参与 LCEL 的 Runnable。
chain = RunnableLambda(add_prefix) | model
```

用于调试中间结果：

```python
def debug_print(value):
    # 打印中间值，方便确认上一环节输出是否符合预期。
    print("当前中间结果：", value)
    # 一定要返回原值，否则后续链拿不到输入。
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
        # 用户问题先进入 retriever 检索，再用 format_docs 拼成上下文。
        "context": retriever | format_docs,
        # 同一个用户问题原样保留下来，作为 prompt 的 question。
        "question": RunnablePassthrough(),
    }
    | prompt
    | model
    | StrOutputParser()
)
```

这段代码可以按步骤理解：

1. 输入是一个普通问题字符串。
2. `"context"` 分支：问题 -> `retriever` -> `format_docs` -> 参考资料文本。
3. `"question"` 分支：`RunnablePassthrough()` 保留原始问题。
4. 两个字段一起传给 `prompt`。
5. 最后经过 `model` 和 `StrOutputParser()` 得到答案字符串。

输入问题会分成两路：一路检索上下文，一路作为 `question` 保留。

### 5. 函数直接入链

简单函数有时可以直接参与 LCEL 组合。

```python
def format_docs(docs):
    # 把多个 Document 的正文拼成一个字符串，作为 RAG 上下文。
    return "\n\n".join(doc.page_content for doc in docs)

chain = retriever | format_docs | prompt | model | StrOutputParser()
```

如果需要更明确的 Runnable 行为，可以使用 `RunnableLambda`。

### 6. assign 与并行输入思路

LCEL 经常需要把一个输入扩展成多个字段，例如 RAG 中把问题同时变成 `context` 和 `question`。

```python
rag_inputs = {
    # context 由检索器结果格式化而来。
    "context": retriever | format_docs,
    # question 是用户原始输入。
    "question": RunnablePassthrough(),
}
```

这个字典表示并行构造多个输入字段：

- `context` 来自检索器结果。
- `question` 保留用户原始输入。

### 7. RunnableParallel 并行节点

`RunnableParallel` 可以让多个 Runnable 接收同一个输入，并行计算后合并成一个字典。字典写法本质上也会被转换成类似的并行结构。

```python
from langchain_core.runnables import RunnableLambda, RunnableParallel

r1 = RunnableLambda(lambda x: x + 1)
r2 = RunnableLambda(lambda x: x * 2)

chain = RunnableParallel(r1=r1, r2=r2)

print(chain.invoke(2))
# {"r1": 3, "r2": 4}
```

RAG 中常见写法：

```python
rag_inputs = RunnableParallel(
    context=retriever | format_docs,
    question=RunnablePassthrough(),
)

rag_chain = rag_inputs | prompt | model | StrOutputParser()
```

适合场景：

- 同一个输入要同时进入多个检索器。
- 同一个问题既要保留原文，又要改写、分类或抽取关键词。
- 多路计算之间没有依赖关系，可以并行提升效率。

### 8. 合并输入和处理中间字典

`RunnablePassthrough.assign()` 常用于在保留原输入字典的基础上新增字段。

```python
from langchain_core.runnables import RunnableLambda, RunnablePassthrough

def build_context(inputs: dict) -> str:
    docs = retriever.invoke(inputs["question"])
    return "\n\n".join(doc.page_content for doc in docs)

chain = (
    RunnablePassthrough.assign(context=RunnableLambda(build_context))
    | prompt
    | model
    | StrOutputParser()
)

answer = chain.invoke({"question": "什么是 RAG？", "user_id": "u001"})
```

这类写法适合业务输入已经是字典的场景，例如：

```text
{"question": "...", "user_id": "...", "tenant_id": "..."}
```

`assign` 会保留已有字段，再新增 `context`。后续 prompt 可以同时使用 `question`、`tenant_id`、`context` 等变量。

### 9. fallback、retry 与容错

链在生产环境中可能因为模型超时、网络波动、解析失败而报错。LCEL 可以给 Runnable 增加 fallback 或 retry。

`with_fallbacks()`：当前 Runnable 失败时，尝试备用 Runnable。

```python
primary_model = openai_model
secondary_model = local_model

safe_model = primary_model.with_fallbacks([secondary_model])

chain = prompt | safe_model | StrOutputParser()
```

`with_retry()`：临时错误时自动重试。

```python
stable_chain = chain.with_retry(stop_after_attempt=3)
```

注意：

- fallback 适合主模型不可用、主工具失败、解析器失败时兜底。
- retry 适合偶发超时和网络错误，不适合业务逻辑错误。
- 重试会增加延迟和成本，线上要设置超时和最大次数。
- 如果工具有副作用，例如写文件、发消息、扣费，不要盲目重试。

### 10. 条件路由

LCEL 可以根据输入动态选择后续链路。简单场景可以用 `RunnableLambda` 返回不同 Runnable。

```python
from langchain_core.runnables import RunnableLambda

math_chain = math_prompt | model | StrOutputParser()
default_chain = default_prompt | model | StrOutputParser()

def route(inputs: dict):
    if "数学" in inputs["question"] or "计算" in inputs["question"]:
        return math_chain.invoke(inputs)
    return default_chain.invoke(inputs)

chain = RunnableLambda(route)
```

更常见的工程结构是：先用一个分类链判断问题类型，再按类型选择知识库、工具或 prompt。

```text
用户问题
-> 分类/路由
-> 产品知识库 / 技术知识库 / 工具调用 / 默认回答
-> 统一输出格式
```

路由适合：

- 多知识库问答。
- 不同问题走不同模型。
- Agent 或 RAG 前置分类。
- 简单问题直接回答，复杂问题进入检索。

### 11. 生命周期监听

`with_listeners()` 可以在 Runnable 开始、结束或报错时执行回调，适合记录日志、耗时、输入输出摘要。

```python
from langchain_core.tracers.schemas import Run

def on_start(run_obj: Run):
    print("链开始：", run_obj.start_time)

def on_end(run_obj: Run):
    print("链结束：", run_obj.end_time)

chain_with_log = chain.with_listeners(
    on_start=on_start,
    on_end=on_end,
)

result = chain_with_log.invoke({"question": "什么是 LCEL？"})
```

使用建议：

- 日志里不要直接打印 API Key、身份证号、手机号等敏感信息。
- 线上日志建议记录 `run_id`、耗时、模型名、token 成本、检索文档 ID。
- 如果需要完整链路追踪，可以接 LangSmith 或项目自己的日志系统。

### 12. 生命周期管理和配置

Runnable 调用时可以传 `config`，常见用途是控制并发、标签、元数据、会话 ID。

```python
result = chain.invoke(
    {"question": "什么是 RAG？"},
    config={
        "tags": ["rag", "demo"],
        "metadata": {"user_id": "u001"},
        "max_concurrency": 3,
    },
)
```

常见配置：

| 配置 | 作用 |
| --- | --- |
| `tags` | 给一次运行打标签，方便追踪 |
| `metadata` | 附加业务信息 |
| `max_concurrency` | 控制批量或并行调用的最大并发 |
| `configurable` | 传入 session_id 等可配置字段 |

`RunnableWithMessageHistory` 常用 `configurable.session_id` 区分不同用户会话。

```python
chain_with_history.invoke(
    {"question": "继续解释一下"},
    config={"configurable": {"session_id": "user-1"}},
)
```

### 13. 链式调用的调试方法

链越长，越需要观察中间结果。

```python
from langchain_core.runnables import RunnableLambda

def inspect_value(value):
    # 调试时把中间值打印出来。
    print("中间值：", value)
    # 返回原值，保证链继续运行。
    return value

chain = prompt | RunnableLambda(inspect_value) | model | StrOutputParser()
```

如果某一步报错，可以把链拆开单独执行：

```python
# 复杂链可以拆开运行，定位是哪一步出问题。
prompt_value = prompt.invoke({"question": "什么是 RAG？"})
model_result = model.invoke(prompt_value)
text = StrOutputParser().invoke(model_result)
```

本阶段小结：

- LCEL 的 `|` 表示上一步输出传给下一步。
- Runnable 统一了 `invoke`、`batch`、`stream` 等调用方式。
- `RunnableLambda` 适合把自定义函数放入链。
- `RunnablePassthrough` 适合保留原始输入。
- `RunnableParallel` 适合把同一个输入并行加工成多个字段。
- `assign` 适合在已有输入字典上追加中间结果。
- `with_fallbacks`、`with_retry`、`with_listeners` 分别用于兜底、重试和日志监听。
- 调试复杂链时，把链拆开逐步检查最稳。

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
    """查询城市天气。

    这个说明会暴露给模型，用来判断什么时候调用工具。
    """
    return f"{city} 今天晴。"
```

这段代码可以按步骤理解：

1. `@tool`：把普通函数注册成 LangChain 工具。
2. `city: str`：告诉模型工具需要一个字符串参数。
3. docstring：告诉模型工具用途。
4. 返回值：工具执行后的观察结果，会传回模型继续推理。

工具说明要写清楚，因为模型会根据名称、参数和 docstring 判断什么时候调用。可以把模型理解为 Agent 的“大脑”，工具就是 Agent 的“手和脚”：模型负责判断要做什么，工具负责连接外部世界并返回结果。

一个工具至少要让模型知道三件事：

| 信息 | 作用 |
| --- | --- |
| 工具名称 | 模型用它来判断工具能力，例如 `get_weather`、`web_search` |
| 工具用途 | 描述什么时候应该调用这个工具 |
| 参数说明 | 告诉模型需要传什么参数、参数含义是什么 |

`@tool` 可以显式指定名称和描述：

```python
from langchain_core.tools import tool


@tool("square_root", description="Calculate the square root of a number")
def calculate_square_root(number: float) -> float:
    # 用普通 Python 完成实际计算。
    return number ** 0.5
```

如果不显式指定，LangChain 通常会根据函数自动推断：

| 信息 | 默认来源 |
| --- | --- |
| 工具名称 | 函数名 |
| 参数 | 函数参数和类型注解 |
| 工具描述 | 函数 docstring |

所以函数命名、类型注解和 docstring 不是装饰，它们会直接影响模型是否能正确使用工具。

带默认参数的工具示例：

```python
from langchain_core.tools import tool


@tool
def get_weather(
    # location 是必填参数。
    location: str,
    # units 有默认值，模型不传时使用 celsius。
    units: str = "celsius",
    # include_forecast 控制是否附带预报。
    include_forecast: bool = False,
) -> str:
    """Get current weather for a location.

    Args:
        location: City name or coordinates.
        units: Temperature unit, celsius or fahrenheit.
        include_forecast: Whether to include a short forecast.
    """
    return f"{location} 当前温度 22 度，单位：{units}"
```

复杂参数可以用 Pydantic 模型描述，这样字段说明更清楚：

```python
from typing import Literal

from langchain_core.tools import tool
from pydantic import BaseModel, Field


class WeatherInput(BaseModel):
    # Literal 限制模型只能在两个单位里选择。
    location: str = Field(description="City name or coordinates")
    units: Literal["celsius", "fahrenheit"] = Field(
        default="celsius",
        description="Temperature unit preference",
    )
    include_forecast: bool = Field(
        default=False,
        description="Include 5-day forecast",
    )


@tool(args_schema=WeatherInput)
def get_weather(location: str, units: str = "celsius", include_forecast: bool = False) -> str:
    """Get weather information for a location."""
    return f"{location} weather, units={units}, forecast={include_forecast}"
```

这段代码可以按步骤理解：

1. `WeatherInput(BaseModel)`：定义工具参数 schema。
2. `Field(description=...)`：解释字段含义，帮助模型填参数。
3. `Literal["celsius", "fahrenheit"]`：限制单位只能二选一。
4. `@tool(args_schema=WeatherInput)`：把 schema 绑定到工具。
5. 函数签名仍然保留参数，真正执行工具时会传入这些值。

字段越清楚，模型越容易构造正确参数。

### 2. 手动执行工具

```python
# 手动执行工具时，传入的是参数字典。
result = get_weather.invoke({"city": "上海"})
print(result)
```

工具调用的关键：

- 参数类型要明确。
- 返回值尽量简单、结构清晰。
- 工具内部要处理异常。
- 不要让工具执行危险操作，尤其是删除、支付、数据库写入等。

### 3. Agent 智能体

Agent 是能够感知输入、进行推理、自主决策并采取行动的智能系统。在 LangChain 中，Agent 会让模型根据任务自行选择工具、决定步骤并生成最终回答。

```python
from langchain.agents import create_agent

agent = create_agent(
    # Agent 使用的模型。
    model=model,
    # Agent 可以选择调用的工具列表。
    tools=[get_weather],
    # 系统提示词约束 Agent 的角色和工具使用方式。
    system_prompt="你是一个可以调用工具的助手。",
)

result = agent.invoke(
    # Agent 输入通常是 messages 字段。
    {"messages": [{"role": "user", "content": "上海天气怎么样？"}]}
)
```

这段代码可以按步骤理解：

1. `create_agent(...)`：创建一个能调用工具的 Agent。
2. `model=model`：让模型负责理解问题和决定动作。
3. `tools=[get_weather]`：把天气工具提供给 Agent。
4. `system_prompt=...`：约束 Agent 行为。
5. `agent.invoke(...)`：运行 Agent，并传入用户消息。

Agent 和普通聊天机器人最大的区别是：普通 LLM 更像“回答问题”，Agent 更像“为了目标去执行任务”。

| 对比项 | 传统聊天机器人 / LLM | AI Agent |
| --- | --- | --- |
| 交互方式 | 被动问答 | 目标驱动，可以主动规划步骤 |
| 能力边界 | 主要生成文本 | 可以调用工具、搜索网页、操作软件、发起业务请求 |
| 人类输入 | 需要人把步骤说清楚 | 用户给最终目标，Agent 自己拆解路径 |
| 决策方式 | 直接根据上下文回答 | 判断是否需要工具、选择工具、观察结果再继续 |
| 适合任务 | 简单问答、写作、总结 | 多步骤任务、实时查询、外部系统操作 |

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
    # 第一轮用户告诉模型自己的名字。
    {"role": "user", "content": "我叫小明"},
    # assistant 的历史回复也要放回去。
    {"role": "assistant", "content": "你好，小明。"},
    # 当前新问题放在最后。
    {"role": "user", "content": "我叫什么？"},
]

result = agent.invoke({"messages": messages})
```

如果没有传历史消息，模型就不知道前文。

### 6. Runtime Context 与结构化输出

Runtime Context 可用于把运行时信息传给工具或 Agent，例如用户 ID、权限、请求来源等。

结构化输出用于让模型按固定格式返回结果，例如 Pydantic 模型、JSON 字段等。适合分类、抽取、表单生成等场景。

### 7. Agent 和普通 Chain 的区别

| 对比项 | Chain | Agent |
| --- | --- | --- |
| 执行流程 | 开发者固定编排 | 模型动态决定步骤 |
| 是否调用工具 | 通常固定 | 根据问题自主选择 |
| 可控性 | 更强 | 更灵活但更难控 |
| 适合场景 | RAG、固定问答、格式转换 | 多工具任务、复杂问题拆解 |

简单说：如果流程明确，用 Chain；如果需要模型自己判断下一步，用 Agent。

### 8. Agent 的核心理解

Agent 可以理解为让大模型从“只会回答”升级为“会做事”的组件。它通常由几部分组成：

```text
Agent = 大语言模型 + 工具集 + 决策逻辑 + 记忆/状态
```

没有 Agent 时，LLM 只能根据自身训练数据和输入上下文回答问题；遇到实时数据、复杂计算、外部系统调用时容易卡住。

有了 Agent 后，LLM 更像一个“调度者”：

```text
理解任务 -> 判断是否需要工具 -> 选择工具 -> 执行工具 -> 观察结果 -> 决定下一步 -> 生成最终答案
```

核心特点：

- **目标驱动**：围绕用户的具体任务目标展开工作。
- **工具调用能力**：通过外部工具弥补 LLM 自身能力边界。
- **自主决策与迭代**：根据工具返回结果决定继续调用工具还是直接回答。
- **可接入记忆**：结合历史消息和状态做多轮任务。

### 9. ReAct 工作范式

ReAct 是 Agent 常见的思考与行动框架，全称可以理解为 Reasoning + Acting，即“推理 + 行动”。

它的典型循环是：

```text
思考 Reasoning -> 行动 Action -> 观察 Observation -> 再思考 -> 再行动 -> ... -> 结束
```

含义：

| 阶段 | 作用 |
| --- | --- |
| Reasoning | 分析问题，判断已有信息是否足够，决定下一步 |
| Action | 调用工具或执行某个动作 |
| Observation | 获取工具返回结果，提取有效信息 |
| Finish | 信息足够后生成最终答案 |

ReAct 的价值是让 Agent 不再直接“拍脑袋回答”，而是通过自然语言思考过程引导工具调用，逐步解决复杂问题。它适合智能客服、报告生成、任务规划、需要多步工具协作的场景。

示意代码：

```python
from langchain.agents import create_agent
from langchain_core.tools import tool


@tool(description="获取体重，返回值是整数，单位千克")
def get_weight() -> int:
    return 90


@tool(description="获取身高，返回值是整数，单位厘米")
def get_height() -> int:
    return 172


agent = create_agent(
    model=model,
    tools=[get_weight, get_height],
    system_prompt=(
        "你是遵循 ReAct 思路的智能体。"
        "遇到需要工具的数据时，先思考，再选择工具，"
        "根据观察结果继续推理，最后给出答案。"
    ),
)

for chunk in agent.stream(
    {"messages": [{"role": "user", "content": "计算我的 BMI"}]},
    stream_mode="values",
):
    latest_message = chunk["messages"][-1]
    if latest_message.content:
        print(latest_message.content)
```

注意：不同 LangChain 版本对 Agent 输出、流式事件和中间步骤展示方式可能不同，项目里要以当前依赖版本为准。

### 10. Agent Middleware 中间件

Middleware 的作用是对 Agent 的每一步执行进行控制、自定义和拦截。可以把它理解为 Agent 执行过程中的钩子。

常见用途：

- 日志记录、分析、调试。
- 转换提示词、调整工具选择。
- 重试、备用模型、提前终止。
- 安全防护、身份校验、权限控制。
- 监控工具调用参数和结果。

常见钩子：

| 钩子 | 作用 |
| --- | --- |
| `before_agent` | Agent 执行前拦截 |
| `after_agent` | Agent 执行后拦截 |
| `before_model` | 模型调用前拦截 |
| `after_model` | 模型调用后拦截 |
| `wrap_model_call` | 包装每次模型调用 |
| `wrap_tool_call` | 包装每次工具调用 |

示意代码：

```python
from langchain.agents import create_agent


def log_before_agent(state, runtime) -> None:
    print(f"[before_agent] messages: {len(state['messages'])}")


def log_after_agent(state, runtime) -> None:
    print(f"[after_agent] messages: {len(state['messages'])}")


def log_before_model(state, runtime) -> None:
    print(f"[before_model] about to call model")


def log_after_model(state, runtime) -> None:
    print("[after_model]", state["messages"][-1].content)


agent = create_agent(
    model=model,
    tools=[get_weather],
    middleware=[
        log_before_agent,
        log_before_model,
        log_after_model,
        log_after_agent,
    ],
)
```

包装工具调用的思路：

```python
def monitor_tool(request, handler):
    print("调用工具：", request.tool_call["name"])
    print("工具参数：", request.tool_call["args"])
    result = handler(request)
    print("工具调用完成")
    return result
```

包装模型调用时可以做重试：

```python
def retry_on_error(request, handler):
    max_retries = 3
    for attempt in range(max_retries):
        try:
            return handler(request)
        except Exception:
            if attempt == max_retries - 1:
                raise
```

中间件能提升可观测性和可控性，但也会增加调试复杂度。学习阶段先理解“在哪些节点可以拦截”，项目阶段再按需要加入日志、重试、安全控制等能力。

### 11. 预置工具：Tavily 网页搜索

Tavily 是 LangChain 中常见的联网搜索工具，适合让 Agent 获取实时信息、新闻、网页资料或参考链接。

使用前通常需要：

```powershell
# 1. 注册 Tavily 账号并创建 API Key
# 2. 配置环境变量
$env:TAVILY_API_KEY="你的 Tavily API Key"

# 3. 安装依赖
uv add langchain-tavily
```

基础用法：

```python
from langchain_tavily import TavilySearch

search_tool = TavilySearch(
    max_results=5,
    topic="general",
)

result = search_tool.invoke({"query": "LangChain Agent memory"})
print(result)
```

也可以封装成自己的工具，让名称和描述更贴近业务：

```python
from langchain_core.tools import tool
from langchain_tavily import TavilySearch

tavily = TavilySearch(max_results=5, topic="general")


@tool
def web_search(query: str) -> str:
    """Search the web for recent information and references."""
    return tavily.invoke({"query": query})
```

如果希望模型最终返回答案和参考链接，可以配合结构化输出：

```python
from pydantic import BaseModel, Field


class Reference(BaseModel):
    title: str = Field(description="参考资料标题")
    url: str = Field(description="参考资料链接")


class AnswerInfo(BaseModel):
    answer: str = Field(description="基于搜索结果生成的回答")
    reference: list[Reference] = Field(description="引用来源列表")
```

Tavily 使用建议：

- 查询实时信息、网页资料时使用；普通计算和内部知识问答不一定需要。
- 搜索结果要让模型引用来源，避免只给一个没有出处的结论。
- 生产环境要限制搜索次数、超时时间和最大返回结果数。
- 搜索结果不等于真相，重要场景要结合来源可信度和多来源交叉验证。

### 12. 工具设计建议

工具函数要让模型“看得懂、用得对”。

```python
@tool
def search_product(keyword: str) -> str:
    """根据商品关键词查询商品资料。keyword 应该是商品名称、品类或属性。"""
    return "查询结果..."
```

建议：

- 工具名使用动词加名词，例如 `search_product`、`get_weather`。
- docstring 写清楚什么时候用、参数是什么、返回什么。
- 参数不要太复杂。
- 工具返回内容尽量短而结构化。
- 涉及写入、删除、支付、发消息等操作时，要加人工确认。

本阶段小结：

- Tool 是模型可调用的外部能力。
- 工具的名称、参数类型、docstring 和 Pydantic 字段说明会影响模型调用质量。
- Agent 适合多工具和不确定步骤的任务。
- Agent 和普通聊天机器人不同，Agent 更强调目标、决策、行动和观察结果。
- ReAct 是常见 Agent 工作范式：思考、行动、观察、再思考。
- Middleware 可以对 Agent、模型和工具调用过程做日志、调试、重试和安全控制。
- Tavily 这类预置工具可以让 Agent 获取联网搜索能力。
- `system_prompt` 是约束 Agent 行为的重要位置。
- 工具说明越清楚，模型越容易正确调用。
- Agent 更灵活，但调试和安全控制也更重要。

## 十一、记忆与聊天历史

### 1. Agent 记忆类型

Agent 的记忆通常分为短期记忆和长期记忆。

| 类型 | 说明 | 常见内容 |
| --- | --- | --- |
| 短期记忆 | 当前任务或当前会话内的上下文 | 本轮对话消息、工具调用结果、临时状态 |
| 长期记忆 | 跨任务、跨会话保留的信息 | 用户偏好、历史经验、知识沉淀、长期档案 |

短期记忆解决的是“这次对话前面说了什么”；长期记忆解决的是“以前发生过什么、用户长期偏好是什么”。

在 LangChain Agent 中，短期记忆通常体现在 `AgentState` 里，`messages` 是其中最核心的部分：

```text
AgentState
  -> messages: 当前会话消息列表
  -> 其它运行时状态：工具结果、中间步骤、自定义字段等
```

调用 Agent 时传入历史消息，就是在给它当前任务的短期记忆：

```python
result = agent.invoke(
    {
        # 这里手动把历史消息和当前问题一起传给 Agent。
        "messages": [
            {"role": "user", "content": "我叫小明"},
            {"role": "assistant", "content": "你好，小明。"},
            {"role": "user", "content": "我叫什么？"},
        ]
    }
)
```

如果没有把历史消息传回去，模型通常不会知道前文。正式项目中，短期记忆还需要考虑消息窗口、摘要压缩和隐私清理。

### 2. 临时记忆

`InMemoryChatMessageHistory` 适合学习和演示，数据只存在内存中，程序重启就丢失。

```python
from langchain_core.chat_history import InMemoryChatMessageHistory

# 创建一个内存聊天历史对象。
history = InMemoryChatMessageHistory()

# 追加用户消息。
history.add_user_message("你好")

# 追加 AI 消息。
history.add_ai_message("你好，有什么可以帮你？")

# 查看当前保存的消息列表。
print(history.messages)
```

### 3. RunnableWithMessageHistory

`RunnableWithMessageHistory` 可以给链增加历史对话能力。

```python
from langchain_core.runnables.history import RunnableWithMessageHistory

# store 用来保存不同 session_id 对应的历史对象。
store = {}


def get_session_history(session_id: str):
    # 如果这个会话第一次出现，就创建一份新的内存历史。
    if session_id not in store:
        store[session_id] = InMemoryChatMessageHistory()
    return store[session_id]

# 给原始 chain 包一层历史管理能力。
chain_with_history = RunnableWithMessageHistory(
    chain,
    # 根据 session_id 找到对应历史。
    get_session_history,
    # 本次用户输入字段名。
    input_messages_key="question",
    # prompt 中 MessagesPlaceholder 使用的字段名。
    history_messages_key="history",
)

result = chain_with_history.invoke(
    {"question": "我叫小明"},
    # session_id 用来区分不同用户或不同会话。
    config={"configurable": {"session_id": "user-1"}},
)
```

这段代码可以按步骤理解：

1. `store = {}`：用字典临时保存会话历史。
2. `get_session_history(session_id)`：根据会话 ID 返回对应历史对象。
3. `RunnableWithMessageHistory(...)`：给链增加自动读写历史的能力。
4. `input_messages_key="question"`：告诉它用户新消息在哪个字段。
5. `history_messages_key="history"`：告诉它历史消息要填到 Prompt 的哪个变量。
6. `session_id="user-1"`：同一个 session_id 会接上同一段历史。

核心是用 `session_id` 区分不同会话。

### 4. 长期会话记忆

长期记忆可以保存到文件、Redis、数据库或其他持久化存储。学习阶段可以用文件保存。

自定义长期记忆类时，核心是继承 `BaseChatMessageHistory`，并实现会话历史需要的几个同步接口。

| 方法/属性 | 作用 |
| --- | --- |
| `messages` | 获取当前会话的历史消息 |
| `add_messages()` | 追加一批新消息 |
| `clear()` | 清空当前会话消息 |

文件版实现思路：

```text
session_id -> 文件名 -> 该会话的消息列表
```

也就是说，不同 `session_id` 会写入不同文件，互不影响。

```python
import json
from pathlib import Path

from langchain_core.chat_history import BaseChatMessageHistory
from langchain_core.messages import BaseMessage, messages_from_dict, message_to_dict


class FileChatMessageHistory(BaseChatMessageHistory):
    def __init__(self, storage_path: str, session_id: str):
        # storage_path 是历史文件保存目录。
        self.storage_path = Path(storage_path)
        # session_id 用来隔离不同会话。
        self.session_id = session_id

    @property
    def file_path(self) -> Path:
        # 每个 session_id 对应一个 JSON 文件。
        return self.storage_path / f"{self.session_id}.json"

    @property
    def messages(self) -> list[BaseMessage]:
        # 文件不存在时，说明这个会话还没有历史。
        if not self.file_path.exists():
            return []
        # 读取 JSON，再转回 LangChain 消息对象。
        data = json.loads(self.file_path.read_text(encoding="utf-8"))
        return messages_from_dict(data)

    def add_messages(self, messages: list[BaseMessage]) -> None:
        # 先读取旧消息，再追加新消息。
        all_messages = self.messages + messages
        # LangChain 消息对象不能直接 JSON 序列化，需要先转成 dict。
        data = [message_to_dict(message) for message in all_messages]
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text(
            json.dumps(data, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def clear(self) -> None:
        # 清空当前 session_id 对应的历史。
        self.storage_path.mkdir(parents=True, exist_ok=True)
        self.file_path.write_text("[]", encoding="utf-8")
```

这个类的关键流程：

1. 读取历史时，如果文件不存在，返回空列表。
2. 追加消息时，先读取旧消息，再合并新消息。
3. 写入文件前，把 LangChain 消息对象转成可 JSON 序列化的字典。
4. 清空历史时，把文件内容写成空数组 `[]`。

如果后续要切换到 Redis 或数据库，通常只需要把 `get_session_history()` 返回的历史对象换掉，链的其它部分可以不变。

生产环境注意：

- 历史记录不能无限增长，需要窗口截断、摘要压缩或长期/短期记忆分层。
- 历史记录可能包含隐私数据，要考虑权限、加密、脱敏和清理策略。
- 多机器或高并发场景应使用 Redis、数据库或专门的会话存储。

### 5. 记忆设计常见方案

| 方案 | 特点 | 适合场景 |
| --- | --- | --- |
| 内存历史 | 简单，重启丢失 | Demo、单次脚本 |
| 文件历史 | 易理解，可持久化 | 本地学习、小工具 |
| Redis 历史 | 读写快，支持过期 | Web 应用、多会话 |
| 数据库历史 | 易查询和审计 | 正式业务系统 |
| 摘要记忆 | 压缩长对话 | 长周期对话 |



### 6. Agent Checkpointer 与 thread_id

新版 LangChain Agent 的短期记忆通常依赖 LangGraph checkpointer。它的核心流程可以记成三步：

```text
1. 导入并初始化 checkpointer
2. 创建 Agent 时传入 checkpointer
3. 调用 Agent 时在 config 中指定 thread_id
```

`thread_id` 可以理解为会话标识。同一个 `thread_id` 会复用同一段短期记忆；不同 `thread_id` 互相隔离。

内存版示例适合学习和演示：

```python
from langchain.agents import create_agent
from langgraph.checkpoint.memory import InMemorySaver

# 内存检查点，适合学习；程序重启后会丢失。
checkpointer = InMemorySaver()

agent = create_agent(
    model=model,
    tools=[],
    # 传入 checkpointer 后，Agent 可以保存线程状态。
    checkpointer=checkpointer,
    system_prompt="你是一个能记住当前会话上下文的助手。",
)

# thread_id 表示当前会话线程。
config = {"configurable": {"thread_id": "thread_1"}}

agent.invoke(
    # 第一次运行：告诉 Agent 用户名。
    {"messages": [{"role": "user", "content": "我叫小明"}]},
    config=config,
)

result = agent.invoke(
    # 第二次运行：同一个 thread_id，因此可以接上前文。
    {"messages": [{"role": "user", "content": "我叫什么？"}]},
    config=config,
)

# 取最后一条消息，通常是 Agent 的最终回答。
print(result["messages"][-1].content)
```

注意：

- `InMemorySaver` 只保存在内存中，程序重启后记忆会丢失。
- `thread_id` 不要每次都生成新的，否则模型无法记住前文。
- Web 应用里通常用用户 ID、会话 ID、租户 ID 组合生成 `thread_id`。

### 7. Checkpointer 持久化存储

生产环境不能只用内存 checkpointer，常见做法是把 checkpoint 存到数据库。官方文档示例常见 Postgres，也可以在本地学习时使用 SQLite。

Postgres 思路示例：

```powershell
uv add langgraph-checkpoint-postgres
```

```python
from langchain.agents import create_agent
from langgraph.checkpoint.postgres import PostgresSaver

# 这里只展示连接字符串写法，不在本文档中执行数据库建表。
DB_URI = "postgresql://postgres:postgres@localhost:5432/postgres?sslmode=disable"

with PostgresSaver.from_conn_string(DB_URI) as checkpointer:
    # 第一次使用时通常需要 setup() 建表。
    # 出于数据库安全要求，学习文档只展示写法，不在本项目中执行。
    # checkpointer.setup()

    agent = create_agent(
        model=model,
        tools=[],
        checkpointer=checkpointer,
    )
```

SQLite 本地学习思路：

```powershell
uv add langgraph-checkpoint-sqlite
```

```python
import sqlite3
from langgraph.checkpoint.sqlite import SqliteSaver

# 本地 SQLite 示例。注意：真实运行会创建或写入 checkpoint.db。
connection = sqlite3.connect("resources/checkpoint.db", check_same_thread=False)
checkpointer = SqliteSaver(connection)

agent = create_agent(
    model=model,
    tools=[],
    checkpointer=checkpointer,
)
```

数据库安全提醒：

- `checkpointer.setup()` 可能创建表，属于数据库结构操作，生产项目必须先确认环境和 SQL。
- 不要在不明确的数据库连接上运行建表、迁移、清空、重建命令。
- 学习阶段建议先用 `InMemorySaver` 或单独的本地 SQLite 演示库。

### 8. 记忆管理策略

多轮对话会让历史消息越来越多，最终超过模型上下文窗口。比如 DeepSeek 的上下文窗口也有上限，不能无限塞历史。常见记忆管理策略有四类：

| 策略 | 含义 | 适合场景 |
| --- | --- | --- |
| Trim 修剪 | 调模型前只保留最近 N 条或按 token 截断 | 快速控制上下文长度 |
| Delete 删除 | 从 AgentState/checkpoint 中永久删除部分消息 | 清理错误、隐私或无用历史 |
| Summarize 总结 | 把早期消息总结成摘要，再保留近期消息 | 长对话、客服、学习助手 |
| Custom 自定义 | 按业务规则筛选消息，例如只保留订单相关内容 | 业务 Agent、复杂权限场景 |

#### 9.1 Trim messages

Trim 是“调用模型之前少传一点”。它不会一定改变数据库里的历史，只是控制这次发给模型的上下文。

```python
from langchain_core.messages import HumanMessage, AIMessage

messages = [
    HumanMessage(content="A"),
    AIMessage(content="B"),
    HumanMessage(content="C"),
    AIMessage(content="D"),
    HumanMessage(content="E"),
]

# 只保留最后 3 条消息，作为本次模型调用上下文。
recent_messages = messages[-3:]
```

#### 9.2 Delete messages

Delete 是从状态里永久移除消息，适合删除错误、敏感或已经不需要的历史。它比 trim 更“重”，要谨慎使用。

```python
# 伪代码：真实项目要根据 LangGraph state/update API 处理
messages = [message for message in messages if message.id not in delete_ids]
```

#### 9.3 Summarize messages

Summarize 是先让模型总结早期历史，再用“摘要 + 最近消息”组成新的上下文。它比 trim 更能保留长期信息，但会引入总结成本和总结误差。

```text
早期消息 -> 总结模型 -> summary
最终上下文 = summary + 最近几轮消息
```

新版 Agent 可以使用内置 `SummarizationMiddleware` 做消息摘要：

```python
from langchain.agents import create_agent
from langchain.agents.middleware import SummarizationMiddleware
from langgraph.checkpoint.memory import InMemorySaver

checkpointer = InMemorySaver()

agent = create_agent(
    model=model,
    tools=[],
    middleware=[
        SummarizationMiddleware(
            # 用哪个模型生成摘要。
            model=model,
            # 当消息 token 达到 4000 左右时触发摘要。
            trigger=("tokens", 4000),
            # 摘要后继续保留最近 20 条原始消息。
            keep=("messages", 20),
        )
    ],
    checkpointer=checkpointer,
)
```

含义：

- `trigger=("tokens", 4000)`：当历史达到一定 token 阈值时触发摘要。
- `keep=("messages", 20)`：摘要后仍保留最近 20 条消息。
- 摘要适合长对话，但关键事实仍建议结构化保存到长期记忆或业务数据库。

#### 9.4 Custom strategies

自定义策略可以按业务规则筛选历史，例如：

- 只保留和当前订单相关的消息。
- 删除用户闲聊，只保留偏好和约束。
- 根据权限过滤工具结果。
- 把用户稳定偏好抽取到长期记忆。

### 9. 长期记忆类型

长期记忆不只是“聊天记录保存很久”，它还可以分成几种类型：

| 记忆类型 | 保存内容 | 人类例子 | Agent 例子 |
| --- | --- | --- | --- |
| Semantic 语义记忆 | 事实 | 学校学到的知识 | 用户偏好、用户资料、业务事实 |
| Episodic 情景记忆 | 经历 | 做过的事情 | 过去执行过的任务、工具调用经验 |
| Procedural 程序性记忆 | 指令和技能 | 肌肉记忆、做事方法 | Agent system prompt、操作流程、策略 |

长期记忆的更新方式也有两类：

| 方式 | 特点 | 适合场景 |
| --- | --- | --- |
| 热路径更新 | 用户请求过程中同步更新记忆，再回答用户 | 需要立刻生效的偏好、关键信息 |
| 后台更新 | 先回答用户，稍后异步整理和写入记忆 | 成本高、耗时长、需要批处理的记忆沉淀 |

实际项目中，短期记忆负责当前会话连贯性，长期记忆负责跨会话的稳定信息。两者最好分开设计，不要把所有东西都塞进 messages。

### 10. session_id 的意义

`session_id` 用来区分不同用户或不同会话。

```text
user-1 -> history/user-1.json
user-2 -> history/user-2.json
```

如果 `session_id` 混用，用户之间的历史可能串在一起；如果每次都生成新的 `session_id`，模型就无法记住前文。

本阶段小结：

- Agent 记忆可分为短期记忆和长期记忆。
- LangChain Agent 的短期上下文通常通过 `AgentState` 中的 `messages` 维护。
- Agent 短期记忆推荐使用 checkpointer，并通过 `thread_id` 区分会话。
- 临时记忆适合演示，生产环境需要 Postgres、SQLite、Redis 等持久化方案。
- 多轮对话的关键是把历史消息重新传给模型。
- `RunnableWithMessageHistory` 通过 `session_id` 管理不同会话。
- 记忆不能无限增长，需要 trim、delete、summarize 或 custom 策略。
- 长期记忆可分为语义记忆、情景记忆和程序性记忆。
- 会话历史可能包含隐私，生产环境要谨慎保存。

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

### 5. RAG 标准流程

完整 RAG 可以拆成 8 步：

1. 准备本地知识文件。
2. 使用 Loader 加载为 `Document`。
3. 使用 TextSplitter 切分为 chunk。
4. 使用 Embedding 模型向量化。
5. 存入 VectorStore。
6. 用户提问时检索相关 chunk。
7. 把检索结果和问题放进 Prompt。
8. 调用 LLM 生成答案。

### 6. RAG Prompt 的基本要求

RAG Prompt 应明确限制模型“只根据资料回答”。

```text
请只根据参考资料回答。
资料不足时不要猜测。
如果参考资料中没有答案，请回答“资料中没有相关信息”。
回答时尽量指出依据。
```

如果不加约束，模型可能会根据常识补全内容，导致答案看起来流畅但不可信。

本阶段小结：

- RAG 的核心是“先检索，再生成”。
- 离线流程负责建库，在线流程负责问答。
- RAG 更适合知识频繁更新的场景，微调更适合改变模型行为。
- chunk、Embedding、Top-k、Prompt 都会影响最终效果。

## 十三、文档加载与文本切分

### 1. Document 对象

LangChain 文档加载器通常返回 `Document` 对象。

| 字段 | 说明 |
| --- | --- |
| `page_content` | 文档正文内容 |
| `metadata` | 元数据，例如来源、页码、行号、业务字段 |

```python
from langchain_core.documents import Document

# Document 是 LangChain RAG 流程里的标准文档对象。
doc = Document(
    # page_content 放正文内容，后续会被切分、向量化和放进 Prompt。
    page_content="Python 是一种简单易学的编程语言。",
    # metadata 放来源、页码、业务 ID 等附加信息。
    metadata={"source": "python_notes.txt", "page": 1},
)
```

`metadata` 可用于展示答案来源、权限过滤、排查检索结果和按分类筛选知识。

### 2. Document Loaders

文档加载器负责把不同格式的数据读取成 `Document` 对象。

LangChain 内置了很多文档加载器，它们可能有不同的初始化参数，但通常都遵循统一接口：

| 方法 | 作用 |
| --- | --- |
| `load()` | 一次性加载全部文档，返回 `list[Document]` |
| `lazy_load()` | 延迟加载，逐个返回文档，适合大文件 |

选择建议：

- 小文件直接用 `load()`，简单清晰。
- 大文件或大量文件优先考虑 `lazy_load()`，避免内存占用过高。
- 加载后先抽样打印 `page_content` 和 `metadata`，确认内容和来源没问题。

```python
# load 会一次性加载全部文档。
docs = loader.load()

# 先检查数量，再抽样看正文和元数据。
print(len(docs))
print(docs[0].page_content[:200])
print(docs[0].metadata)
```

`load()` 与 `lazy_load()` 的区别：

| 方法 | 返回形式 | 优点 | 注意点 |
| --- | --- | --- | --- |
| `load()` | `list[Document]` | 简单直接 | 大文件可能一次性占用较多内存 |
| `lazy_load()` | 迭代器/生成器 | 分批读取，节省内存 | 使用时需要循环消费 |

```python
# lazy_load 适合大文件或大量文件，边读边处理。
for document in loader.lazy_load():
    print(document.page_content[:100])
```

文档加载器一般继承自基础 Loader 类，并最终返回 `Document` 类型对象。RAG 项目里，不管原始文件是 CSV、JSON、TXT 还是 PDF，进入后续流程时都应该统一成 `Document`。

### 3. CSVLoader

`CSVLoader` 用于加载 CSV 文件。每一行通常会被转换成一个 `Document`。

```python
from langchain_community.document_loaders.csv_loader import CSVLoader

loader = CSVLoader(
    # CSV 文件路径。
    file_path="./data/info.csv",
    # 中文文件一般显式指定 utf-8。
    encoding="utf-8",
    # 把 source 这一列写入 Document.metadata["source"]。
    source_column="source",
)

# 每一行通常会被加载成一个 Document。
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

常用参数说明：

| 参数 | 说明 |
| --- | --- |
| `file_path` | CSV 文件路径 |
| `encoding` | 文件编码，例如 `utf-8` |
| `source_column` | 指定哪一列作为来源信息写入 `metadata` |
| `csv_args` | 传给 Python `csv` 模块的解析参数 |

`csv_args` 常见字段：

| 字段 | 说明 |
| --- | --- |
| `delimiter` | 分隔符，例如逗号、制表符 |
| `quotechar` | 字符串包裹符号 |
| `fieldnames` | 字段列表，无表头 CSV 才常用 |

如果数据中有“来源列”，建议配置 `source_column`。这样后续 RAG 回答时可以告诉用户答案来自哪条资料。

### 4. JSONLoader

`JSONLoader` 用于把 JSON 或 JSON Lines 数据加载成 `Document`。它依赖 `jq` 语法抽取字段。

使用前通常需要安装 `jq` 相关依赖：

```powershell
pip install jq
```

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
    # JSON 文件路径。
    file_path="./data/user.json",
    # jq_schema="." 表示取整个 JSON 对象。
    jq_schema=".",
    # 抽取结果不是纯字符串时，通常设为 False。
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

主要参数：

| 参数 | 说明 |
| --- | --- |
| `file_path` | JSON 文件路径，必填 |
| `jq_schema` | jq 抽取语法，必填 |
| `text_content` | 抽取结果是否必须是字符串，默认 `True` |
| `json_lines` | 是否为 JSON Lines 文件，默认 `False` |

`text_content` 的选择：

- 抽取结果是普通字符串时，可以用 `text_content=True`。
- 抽取结果是对象、数组、数字等非字符串时，通常用 `text_content=False`。

JSON Lines 文件的特点是：每一行都是一个独立 JSON 对象，不是整个文件一个大数组。

### 5. TextLoader

`TextLoader` 是最基础的文本加载器，用于读取 `.txt`、`.md` 等纯文本文件，并把文件内容放进一个 `Document`。

```python
from langchain_community.document_loaders import TextLoader

# TextLoader 会把整个文本文件读成 Document。
loader = TextLoader("./data/python_notes.txt", encoding="utf-8")
docs = loader.load()
```

一般会把整个文本文件内容放入一个 `Document`，后续通常要切分。

常见检查：

```python
print(len(docs))                 # 通常为 1
print(docs[0].page_content[:200])
print(docs[0].metadata)
```

### 6. PyPDFLoader

`PyPDFLoader` 用于读取 PDF 文件，依赖 `pypdf`。

依赖安装命令：

```powershell
pip install pypdf
```

```python
from langchain_community.document_loaders import PyPDFLoader

loader = PyPDFLoader(
    # PDF 文件路径。
    file_path="./data/manual.pdf",
    # page 表示按页生成 Document。
    mode="page",
    # 没有密码就传 None。
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

PDF 加载后一定要抽样检查，因为 PDF 的文字顺序、页眉页脚、表格结构经常会影响后续检索效果。

### 7. RecursiveCharacterTextSplitter

文档加载后通常要切成多个 chunk，便于向量检索和控制上下文长度。

`RecursiveCharacterTextSplitter` 是常用的递归字符文本分割器，主要用于按自然段落切分大文档。它会按分隔符优先级逐层尝试切分，在保持上下文完整性和控制片段大小之间取得平衡。

它适合作为 RAG 入门阶段的默认文本切分器，开箱即用效果通常不错。

```python
from langchain_community.document_loaders import TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

loader = TextLoader("./data/python_notes.txt", encoding="utf-8")
docs = loader.load()

splitter = RecursiveCharacterTextSplitter(
    # 每个 chunk 尽量不超过 500 个字符。
    chunk_size=500,
    # 相邻 chunk 重叠 50 个字符，减少上下文断裂。
    chunk_overlap=50,
    # 按优先级依次尝试这些分隔符。
    separators=["\n\n", "\n", "。", "！", "？", "，", " ", ""],
    # 用 Python len 计算长度。
    length_function=len,
)

# 把原始 Document 切成更小的 Document 列表。
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

参数理解：

- `chunk_size=500` 表示每个片段尽量不超过 500 个字符。
- `chunk_overlap=50` 表示相邻片段允许重叠 50 个字符，减少上下文断裂。
- `separators` 越靠前优先级越高，通常先按段落、换行、句号切，再按空格或字符兜底。
- `length_function=len` 表示用 Python 的 `len()` 计算长度。

切分效果检查：

```python
for i, doc in enumerate(split_docs[:3]):
    # 抽样检查前 3 个 chunk，确认切分效果。
    print("chunk", i)
    print(doc.page_content)
    print(doc.metadata)
    print("-" * 20)
```

切分经验：

- chunk 太小：语义不完整，模型回答容易缺上下文。
- chunk 太大：检索不精准，还会占用更多上下文窗口。
- overlap 太小：跨段信息可能断裂。
- overlap 太大：重复内容多，检索结果容易冗余。

本阶段小结：

- Loader 把各种格式文件变成 `Document`。
- `page_content` 是正文，`metadata` 是来源和附加信息。
- CSV、JSON、TXT、PDF 都有对应加载器。
- `load()` 简单，`lazy_load()` 更适合大文件。
- 文本切分是 RAG 效果的重要影响因素。

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
    # 点积：衡量两个向量方向是否一致。
    dot = sum(x * y for x, y in zip(a, b))
    # 分别计算两个向量的长度。
    norm_a = math.sqrt(sum(x * x for x in a))
    norm_b = math.sqrt(sum(y * y for y in b))
    # 点积除以长度乘积，就是余弦相似度。
    return dot / (norm_a * norm_b)
```

向量可以粗略理解为“方向 + 长度”：

- 方向更接近，语义通常更相似。
- 长度有时包含强度信息，但文本检索中更常关注方向。
- 余弦相似度的范围通常在 `-1` 到 `1` 之间，越接近 `1` 越相似。

示例：

```text
"Python 入门" 和 "Python 基础教程" 的方向可能很接近。
"Python 入门" 和 "今天吃什么" 的方向通常差别很大。
```

### 3. LangChain Embeddings

```python
# 示例：根据项目实际供应商替换
# from langchain_openai import OpenAIEmbeddings
# embeddings = OpenAIEmbeddings(model="text-embedding-3-small")

# 查询文本向量化，通常用于用户问题。
vector = embeddings.embed_query("Python 是不是简单易学？")

# 文档批量向量化，通常用于知识库入库。
vectors = embeddings.embed_documents(["Python 入门", "LangChain RAG"])
```

`embed_query()` 和 `embed_documents()` 的区别：

| 方法 | 输入 | 用途 |
| --- | --- | --- |
| `embed_query()` | 单个问题字符串 | 查询向量化 |
| `embed_documents()` | 多个文档字符串 | 文档批量向量化 |

在 RAG 中，文档和问题最好使用同一个 Embedding 模型，否则向量空间可能不一致。

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

典型向量存储流程：

```text
索引阶段：
Documents -> Embedding model -> Embedding vectors -> Vector Store

查询阶段：
Query text -> Embedding model -> Query vector -> Similarity Search -> Top-k results
```

也就是：

- 建库时，把文档转成向量并存起来。
- 查询时，把用户问题也转成向量。
- 用问题向量和文档向量做相似度匹配。
- 返回最相关的前 `k` 条文档。

### 5. InMemoryVectorStore

内存向量存储适合学习和临时演示。

```python
from langchain_core.vectorstores import InMemoryVectorStore

# 内存向量库，只适合学习和临时演示。
vector_store = InMemoryVectorStore(embedding=embeddings)

ids = vector_store.add_documents(
    # 添加切分后的文档。
    documents=split_docs,
    # 给每个 chunk 一个稳定 ID，方便后续删除或更新。
    ids=[f"doc-{i}" for i in range(len(split_docs))],
)

# 相似度搜索会返回最相关的前 3 个 Document。
results = vector_store.similarity_search("Python 是不是简单易学？", k=3)
```

数据只在内存中，程序结束就丢失，不适合生产知识库。

常见操作：

```python
# 添加文档，并指定 id
vector_store.add_documents(
    documents=[doc1, doc2],
    ids=["id1", "id2"],
)

# 删除文档
vector_store.delete(ids=["id1"])

# 相似度搜索
similar_docs = vector_store.similarity_search("your query here", k=4)
```

`ids` 是后续更新和删除的关键。学习时可以用 `id1`、`id2`，项目中建议使用业务 ID。

### 6. Chroma 向量存储

Chroma 是常见的本地/外部向量数据库选择之一。

```python
from langchain_chroma import Chroma

vector_store = Chroma(
    # collection 相当于知识库名称。
    collection_name="example_collection",
    # Chroma 用这个 embedding_function 把文本转向量。
    embedding_function=embeddings,
    # 本地持久化目录。
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

Chroma 与内存向量库的区别：

| 对比项 | InMemoryVectorStore | Chroma |
| --- | --- | --- |
| 存储位置 | 内存 | 本地目录或外部服务 |
| 程序重启后数据 | 丢失 | 可持久化 |
| 适合场景 | 学习、Demo、临时测试 | 本地知识库、原型项目 |
| 配置重点 | Embedding 模型 | collection、embedding、persist_directory |

注意：如果更换了 Embedding 模型，已有 Chroma 数据通常需要重建，否则新旧向量可能不在同一语义空间中。

### 7. add_texts 与 add_documents

如果已经有 `Document`，用 `add_documents()` 更方便保留元数据。

```python
vector_store.add_documents(documents=split_docs, ids=ids)
```

如果只有字符串列表，可以用 `add_texts()`。

```python
vector_store.add_texts(
    # 直接添加字符串，不需要提前创建 Document。
    texts=[
        "减肥需要少吃多练。",
        "运动期间要控制饮食并保持规律作息。",
    ],
    # metadatas 会变成每条文本对应的 Document.metadata。
    metadatas=[
        {"source": "health-1"},
        {"source": "health-2"},
    ],
    # ids 用于后续更新和删除。
    ids=["text-1", "text-2"],
)
```

### 8. Retriever 检索器

向量库可以转为 Retriever，方便接入 RAG 链。

```python
# 把向量库包装成 Retriever，方便接入 LCEL / RAG 链。
retriever = vector_store.as_retriever(
    # k=3 表示返回最相关的 3 条。
    search_kwargs={"k": 3}
)

docs = retriever.invoke("Python 怎么学习？")
```

Retriever 的输出通常是 `list[Document]`。

### 9. 检索参数选择

常见检索参数：

| 参数 | 说明 |
| --- | --- |
| `k` | 返回最相似的前几条 |
| `score_threshold` | 过滤低相似度结果 |
| `filter` | 按元数据过滤，例如分类、用户权限、文件来源 |

示例：

```python
retriever = vector_store.as_retriever(
    search_kwargs={
        "k": 5,
        "filter": {"category": "product"},
    }
)
```

如果检索结果太少，可以增大 `k`；如果上下文太杂，可以减小 `k` 或增加过滤条件。

本阶段小结：

- Embedding 把文本转成向量。
- 向量库负责存储向量并做相似度搜索。
- `InMemoryVectorStore` 适合演示，Chroma 适合本地持久化。
- `add_documents()` 能保留 `Document.metadata`。
- `as_retriever()` 是向量库接入 RAG 链的常见入口。

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

这个 Prompt 的关键点是：

1. 明确角色：知识库助手。
2. 明确依据：只能根据 `{context}`。
3. 明确兜底：资料没有就说没有，不编造。
4. 明确输入：`{context}` 是检索资料，`{question}` 是用户问题。

### 2. 手动检索并回答

```python
from langchain_core.output_parsers import StrOutputParser

question = "这件衣服适合冬天穿吗？"

# 第一步：先用用户问题去向量库检索相关文档。
retrieved_docs = vector_store.similarity_search(question, k=3)

# 第二步：把检索到的 Document 拼成 Prompt 里的 context。
context = "\n\n".join(
    f"来源：{doc.metadata.get('source', '未知')}\n内容：{doc.page_content}"
    for doc in retrieved_docs
)

# 第三步：Prompt -> Model -> 字符串输出。
chain = prompt | model | StrOutputParser()

# 第四步：把 context 和 question 一起交给 RAG 链。
answer = chain.invoke({"context": context, "question": question})
```

### 3. Retriever + RunnablePassthrough

```python
from langchain_core.output_parsers import StrOutputParser
from langchain_core.runnables import RunnablePassthrough


def format_docs(docs):
    # 把 Retriever 返回的 Document 列表转成一段可放进 Prompt 的文本。
    return "\n\n".join(
        f"来源：{doc.metadata.get('source', '未知')}\n内容：{doc.page_content}"
        for doc in docs
    )

# 先把向量库转成检索器。
retriever = vector_store.as_retriever(search_kwargs={"k": 3})

rag_chain = (
    {
        # context 分支：问题 -> 检索 -> 格式化文档。
        "context": retriever | format_docs,
        # question 分支：保留用户原始问题。
        "question": RunnablePassthrough(),
    }
    | prompt
    | model
    | StrOutputParser()
)

answer = rag_chain.invoke("这款商品有什么尺码？")
```

这段代码可以按步骤理解：

1. 用户输入一个问题字符串。
2. `retriever | format_docs` 用问题检索资料，并拼成上下文。
3. `RunnablePassthrough()` 把原始问题保留下来。
4. 字典同时生成 `context` 和 `question` 两个 Prompt 变量。
5. 最后经过 `prompt | model | StrOutputParser()` 得到答案。

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
    # 商品资料 CSV。
    file_path="./data/products.csv",
    encoding="utf-8",
    # source 列会进入 metadata，后面可以展示答案来源。
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

# 为每个 chunk 生成稳定 ID。
ids = [f"product-doc-{i}" for i in range(len(split_docs))]

# 写入向量库，后续在线问答直接检索这个库。
vector_store.add_documents(documents=split_docs, ids=ids)
```

### 7. 返回答案来源

```python
question = "商品A支持退换货吗？"

# 先检索和问题相关的文档。
docs = retriever.invoke(question)

# 再把文档格式化为 Prompt 上下文。
context = format_docs(docs)
answer = chain.invoke({"context": context, "question": question})

# 去重收集来源，方便展示给用户。
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

### 10. RAG 项目文件结构建议

一个简单 RAG 项目可以这样组织：

```text
project/
  data/
    products.csv
    manuals/
  vector_db/
  app.py
  ingest.py
  rag_chain.py
  settings.py
```

职责拆分：

| 文件 | 作用 |
| --- | --- |
| `ingest.py` | 加载文件、切分文本、写入向量库 |
| `rag_chain.py` | 构建 Retriever、Prompt 和问答链 |
| `app.py` | 命令行、Web 页面或 API 入口 |
| `settings.py` | 模型名、路径、Top-k 等配置 |

### 11. RAG 服务拆分思路

当 RAG 项目从脚本变成应用时，建议按职责拆成几个服务类。

离线入库侧可以拆成：

| 模块/类 | 作用 |
| --- | --- |
| `app_file_upload.py` | Streamlit 上传页面，接收用户上传文件 |
| `KnowledgeBaseService` | 处理文件内容、去重、切分、入库 |
| `check_md5()` | 判断文件是否已上传过 |
| `save_md5()` | 保存文件指纹，避免重复入库 |
| `upload_by_str()` | 把文本内容切分后写入向量库 |
| `Chroma` | 保存知识向量 |

离线流程可以理解为：

```text
用户上传文件
-> st.file_uploader()
-> uploader_file.get_value()
-> KnowledgeBaseService
-> 文本切分
-> Chroma 向量库
```

为了避免重复上传同一个文件，可以对文件内容计算 md5：

```python
import hashlib


def get_string_md5(text: str) -> str:
    return hashlib.md5(text.encode("utf-8")).hexdigest()
```

注意：md5 不是安全加密，只适合做文件内容指纹和重复检测，不适合保存密码。

在线问答侧可以拆成：

| 模块/类 | 作用 |
| --- | --- |
| `VectorStoreService` | 管理向量库和 Retriever |
| `get_retriever()` | 返回检索器，供 RAG 链使用 |
| `RagService` | 组装 Prompt、模型、Retriever 和执行链 |
| `_get_chain()` | 创建或返回 RAG 执行链 |
| `FileChatMessageHistory` | 保存聊天历史 |
| `app_qa.py` | Streamlit 聊天 UI |

在线流程可以理解为：

```text
用户在页面提问
-> app_qa.py
-> RagService.chain.invoke()
-> VectorStoreService.get_retriever()
-> Chroma 检索相关文档
-> Prompt + ChatModel 生成答案
-> FileChatMessageHistory 保存消息
-> 页面展示答案
```

服务拆分的好处：

- 上传入库和在线问答互不干扰。
- 向量库逻辑集中在 `VectorStoreService`，方便替换 Chroma。
- Prompt、模型和链集中在 `RagService`，方便调试。
- 聊天历史单独封装，方便从文件切换到 Redis 或数据库。

### 12. 离线流程和在线流程分开写

离线入库脚本只在知识更新时运行：

```python
def build_knowledge_base():
    docs = loader.load()
    split_docs = splitter.split_documents(docs)
    vector_store.add_documents(split_docs, ids=ids)
```

在线问答逻辑每次用户提问都会运行：

```python
def answer_question(question: str) -> dict:
    docs = retriever.invoke(question)
    context = format_docs(docs)
    answer = chain.invoke({"context": context, "question": question})
    return {
        "answer": answer,
        "sources": [doc.metadata.get("source") for doc in docs],
    }
```

不要每次用户提问都重新加载全部文件并重建向量库，否则速度会很慢。

### 13. Prompt 约束模板

商品知识库、制度问答、课程资料问答都可以使用类似约束。

```text
你是一个基于本地知识库回答问题的助手。
规则：
1. 只能根据参考资料回答。
2. 参考资料没有的信息，回答“资料中没有相关信息”。
3. 不要编造商品属性、价格、库存、政策。
4. 如果资料之间有冲突，请说明冲突。
5. 回答后列出参考来源。
```

### 14. 智能体项目结构示例

如果项目进一步升级为 Agent 应用，可以按“工具、RAG、模型、配置、工具函数、页面入口”拆分。

```text
agent_project/
  agent/
    tools/
      agent_tools.py
    middleware.py
    react_agent.py
  config/
  data/
  model/
    factory.py
  prompts/
  rag/
    rag_service.py
    vector_store.py
  utils/
    chain_debug.py
    config_handler.py
    file_handler.py
    logger_handler.py
    path_tools.py
    prompt_loader.py
  app.py
```

典型职责：

| 模块 | 作用 |
| --- | --- |
| `agent_tools.py` | 定义 Agent 可调用工具，例如天气、位置、用户信息、RAG 总结 |
| `middleware.py` | 定义日志、模型调用、工具调用等中间件 |
| `react_agent.py` | 创建 Agent，执行流式输出 |
| `rag_service.py` | RAG 摘要、文档检索、Prompt 加载 |
| `vector_store.py` | 文档加载、文本切分、Retriever 管理 |
| `factory.py` | 创建聊天模型和 Embedding 模型 |
| `prompt_loader.py` | 统一加载 Prompt 文本 |
| `app.py` | Streamlit 或其他 Web 入口 |

一个智能体项目的调用关系可以概括为：

```text
app.py
-> ReactAgent
-> agent_tools / middleware
-> RagSummarizeService
-> VectorStoreService
-> model factory
```

也就是说，Agent 负责调度，工具提供能力，RAG 提供知识，模型工厂提供模型实例，页面只负责交互。

本阶段小结：

- RAG 项目要把建库和问答分开。
- 项目变大后，建议拆分 `KnowledgeBaseService`、`VectorStoreService`、`RagService` 等服务。
- 商品知识库需要稳定的文档 ID 和来源字段。
- 用户答案最好返回来源，便于排查和追溯。
- 更新知识时要考虑新增、删除、重建和 collection 切换。
- Prompt 约束是降低幻觉的重要手段。
- Agent 项目应把工具、中间件、RAG、模型工厂、页面入口分层组织。

## 十六、Streamlit + LangChain 常见模式

Streamlit 适合快速做大模型应用页面。

常见结构：

```python
import streamlit as st

st.title("知识库问答")

# chat_input 会在用户提交问题时返回字符串，否则返回 None。
question = st.chat_input("请输入问题")
if question:
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        # 调用 RAG 链得到答案。
        answer = rag_chain.invoke(question)
        st.write(answer)
```

常见注意点：

- 用 `st.session_state` 保存页面状态和聊天记录。
- 模型调用要加 loading 提示。
- API Key 不要写死在页面代码里。
- RAG 应用最好展示引用来源。

### 1. session_state 保存聊天记录

```python
import streamlit as st

# session_state 在页面重跑时仍能保留数据。
if "messages" not in st.session_state:
    st.session_state.messages = []

# 先把历史消息重新渲染出来。
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.write(message["content"])

question = st.chat_input("请输入问题")

if question:
    # 保存用户新消息。
    st.session_state.messages.append({"role": "user", "content": question})
    # 调用后端链生成回答。
    answer = rag_chain.invoke(question)
    # 保存助手回复。
    st.session_state.messages.append({"role": "assistant", "content": answer})
    # 重新运行脚本，让页面展示最新消息。
    st.rerun()
```

### 2. 展示 RAG 来源

如果后端返回结构是 `{"answer": "...", "sources": [...]}`，页面可以这样展示：

```python
# 后端返回答案和来源列表。
result = answer_question(question)

st.write(result["answer"])

with st.expander("参考来源"):
    for source in result["sources"]:
        # 展示每条来源，便于用户追溯答案依据。
        st.write(source)
```

### 3. Streamlit 常见坑

| 问题 | 原因 | 处理方式 |
| --- | --- | --- |
| 页面每次交互都重新执行 | Streamlit 运行机制如此 | 用 `st.session_state` 保存状态 |
| 聊天记录丢失 | 没有保存到 session_state | 初始化并追加 messages |
| 页面卡住 | 模型调用耗时 | 使用 `st.spinner()` |
| 密钥泄露 | API Key 写在代码里 | 使用环境变量或 secrets |

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

### 7. 依赖或导入路径报错

LangChain 拆包后，很多类的导入路径发生过变化。

处理思路：

1. 先看报错中提示的新导入路径。
2. 检查当前项目安装的包版本。
3. 优先查看官方文档。
4. 尽量使用当前项目已有的导入风格。

常见包：

```text
langchain-core
langchain-community
langchain-openai
langchain-text-splitters
langchain-chroma
```

### 8. 向量库结果和预期不一致

排查方向：

- 是否连接了正确的 `persist_directory`。
- 是否使用了正确的 `collection_name`。
- 文档是否重复入库。
- 删除旧文档时 ID 是否一致。
- Embedding 模型是否前后更换过。

Embedding 模型更换后，旧向量通常应该重建，否则新旧向量不在同一语义空间中。

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
- Tavily Search Tool: <https://docs.langchain.com/oss/python/integrations/tools/tavily_search>
- Structured Output: <https://docs.langchain.com/oss/python/langchain/structured-output>
- Ollama Docs: <https://docs.ollama.com/>

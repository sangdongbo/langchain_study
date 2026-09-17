# Python Deep Agents 入门到复杂业务：采购申请智能评审

这份 notebook 改成“逐步看懂”的版本。

你可以按顺序执行，每一步只新增一个概念：

```text
第 1 层：不用 Agent，只用普通 Python 跑通业务规则
第 2 层：把完整业务链路包装成 1 个工具，交给 Deep Agent 调用
第 3 层：把业务链路拆成多个工具，让 Deep Agent 自己编排
第 4 层：进阶，使用子 Agent 和报告文件
```

这样先知道代码在干什么，再理解 Deep Agents 解决了什么问题。

本案例不是 RAG。它模拟一个企业内部采购申请评审流程：

```text
采购申请 -> 库存检查 -> 供应商风险 -> 预算检查 -> 合规检查 -> 审批路径 -> 最终建议
```

依赖项目根目录 `.env`：

- `DEEPSEEK_API_KEY`：DeepSeek Chat 模型。
- `DEEPSEEK_BASE_URL`：可选，默认 `https://api.deepseek.com`。
- `DEEPSEEK_MODEL` / `OPENAI_MODEL`：可选。
- `DASHSCOPE_API_KEY`：可选，只做 embedding 连通性检查，不影响主线。


## 1. 安装与环境检查

这个单元只做一件事：确认 notebook 需要的包存在。

如果你已经安装过，它只会打印“已安装”。


```python
import importlib.util
import subprocess
import sys


def ensure_package(import_name: str, pip_name: str | None = None) -> None:
    """如果依赖不存在，就在当前 notebook 使用的 Python 环境里安装。"""
    if importlib.util.find_spec(import_name):
        print(f"{import_name} 已安装")
        return

    package = pip_name or import_name
    print(f"正在安装 {package} ...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", package])


ensure_package("deepagents")
ensure_package("langchain_openai", "langchain-openai")
ensure_package("dotenv", "python-dotenv")

print("依赖检查完成。")
```


## 2. 读取 `.env` 并创建 DeepSeek 模型

这个单元容易出错，所以写得稍微啰嗦一点。

重点：

- 从当前目录向上查找 `.env`，避免 notebook 在 `docs` 目录启动时读错位置。
- DeepSeek 默认使用官方地址 `https://api.deepseek.com`。
- 不默认读取 `OPENAI_BASE_URL`，避免拿到本机代理地址。


```python
import os
from pathlib import Path

from dotenv import load_dotenv
from langchain_openai import ChatOpenAI, OpenAIEmbeddings


def find_project_env(start: Path | None = None) -> Path:
    """从当前目录向上查找项目根目录里的 .env。"""
    current = (start or Path.cwd()).resolve()
    for directory in [current, *current.parents]:
        env_path = directory / ".env"
        if env_path.exists():
            return env_path
    raise FileNotFoundError(f"从 {current} 向上没有找到 .env，请确认项目根目录存在 .env。")


ENV_PATH = find_project_env()
PROJECT_ROOT = ENV_PATH.parent
load_dotenv(ENV_PATH, override=True)
print(f"已加载 .env: {ENV_PATH}")


def build_deepseek_chat_model() -> ChatOpenAI:
    """创建 DeepSeek Chat 模型。"""
    api_key = os.getenv("DEEPSEEK_API_KEY")
    if not api_key:
        raise RuntimeError("请先在项目 .env 中配置 DEEPSEEK_API_KEY。")

    # 默认使用 DeepSeek 官方地址；只有你显式配置 DEEPSEEK_BASE_URL 时才覆盖。
    base_url = os.getenv("DEEPSEEK_BASE_URL") or "https://api.deepseek.com"

    # 兼容一些误填成 /anthropic 的情况。
    if base_url.rstrip("/").endswith("/anthropic"):
        base_url = base_url.rstrip("/")[: -len("/anthropic")]

    model = os.getenv("DEEPSEEK_MODEL") or os.getenv("OPENAI_MODEL") or "deepseek-chat"
    print(f"DeepSeek Chat: model={model}, base_url={base_url}")

    return ChatOpenAI(
        model=model,
        api_key=api_key,
        base_url=base_url,
        temperature=0,
        timeout=float(os.getenv("DEEPSEEK_TIMEOUT", "120")),
        max_retries=int(os.getenv("DEEPSEEK_MAX_RETRIES", "2")),
    )


llm = build_deepseek_chat_model()
response = llm.invoke("只回答两个字：成功")
print("模型返回：", response.content)
```


## 3. 可选：DASHSCOPE Embedding 连通性检查

采购评审主线不依赖 embedding。

这个单元只是确认 `.env` 里的百炼配置能用。你不想测 embedding，可以跳过这一节。


```python
def build_dashscope_embeddings() -> OpenAIEmbeddings:
    """创建百炼 text-embedding-v4 embedding 模型。"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("请先在项目 .env 中配置 DASHSCOPE_API_KEY。")

    # 百炼 embedding 批量上限通常不能超过 10，这里强制保护一下。
    batch_size = int(os.getenv("DASHSCOPE_EMBEDDING_BATCH_SIZE", "10"))
    batch_size = max(1, min(batch_size, 10))

    return OpenAIEmbeddings(
        model=os.getenv("DASHSCOPE_EMBEDDING_MODEL", "text-embedding-v4"),
        api_key=api_key,
        base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        dimensions=int(os.getenv("DASHSCOPE_EMBEDDING_DIMENSIONS", "1024")),
        check_embedding_ctx_length=False,
        chunk_size=batch_size,
    )


embeddings = build_dashscope_embeddings()
vec = embeddings.embed_query("采购申请评审需要综合库存、预算、供应商和合规规则。")
print("embedding 维度:", len(vec))
print("前 8 维:", vec[:8])
```


## 4. 加载业务数据

数据文件模拟几个企业系统：

| 数据模块 | 模拟的真实系统 |
| --- | --- |
| `request_examples` | 采购申请表单 |
| `inventory` | 库存 / 资产系统 |
| `suppliers` | 供应商主数据 / 风控系统 |
| `budgets` | 预算系统 |
| `approval_matrix` | 审批矩阵 |
| `compliance_rules` | 合规规则 |

先只看数据，不要急着看 Agent。


```python
import json
from pprint import pprint


DATA_PATH = PROJECT_ROOT / "docs" / "sample_docs" / "procurement_business_data.json"
procurement_data = json.loads(DATA_PATH.read_text(encoding="utf-8"))

print("业务数据文件:", DATA_PATH)
print("数据模块:", list(procurement_data.keys()))
print("\n示例采购申请:")
pprint(procurement_data["request_examples"][0], width=120)
```


## 5. 先定义几个小函数，不碰 Agent

下面这些函数就是“业务系统接口”的模拟版。

你可以先把它们理解成普通 Python 函数：

```text
parse_purchase_request  解析申请
check_inventory         查库存
check_supplier          查供应商
check_budget            查预算
compliance_check        查合规
build_approval_route    算审批路径
```

Deep Agent 后面只是负责“什么时候调用哪个函数”。


```python
def pretty_json(data) -> str:
    """把 dict/list/JSON 字符串格式化打印，方便 notebook 里看结果。"""
    if isinstance(data, str):
        data = json.loads(data)
    return json.dumps(data, ensure_ascii=False, indent=2)


def parse_purchase_request(request_text: str) -> dict:
    """解析采购申请文本，返回结构化采购需求。

    为了让重点放在 Deep Agents，这里使用样例数据作为基础，
    只从用户文本里演示提取数量，例如“4 台”。
    """
    request = dict(procurement_data["request_examples"][0])

    # 简单演示：如果用户文本里出现“2 台/4 台/6 台”，就覆盖样例数量。
    for quantity in [1, 2, 3, 4, 5, 6, 8, 10]:
        if f"{quantity}台" in request_text or f"{quantity} 台" in request_text:
            request["quantity"] = quantity
            break

    request["total_amount"] = request["quantity"] * request["unit_price"]
    return request


def check_inventory(item: str, quantity: int) -> str:
    """查询库存可用性。返回 JSON 字符串，便于 Agent 稳定读取。"""
    for row in procurement_data["inventory"]:
        if row["item"] == item:
            net_available = row["available_quantity"] - row["reserved_quantity"]
            return json.dumps(
                {
                    "item": item,
                    "requested_quantity": quantity,
                    "net_available": net_available,
                    "enough": net_available >= quantity,
                    "lead_time_days": row["lead_time_days"],
                    "replacement_options": row["replacement_options"],
                },
                ensure_ascii=False,
            )
    return json.dumps({"item": item, "found": False, "message": "库存系统中没有该物品。"}, ensure_ascii=False)


def check_supplier(supplier_name: str) -> str:
    """查询供应商风险、合同状态、交付评分和付款条件。"""
    for row in procurement_data["suppliers"]:
        if row["name"] == supplier_name:
            return json.dumps(row, ensure_ascii=False)
    return json.dumps({"name": supplier_name, "found": False, "risk_level": "unknown"}, ensure_ascii=False)


def check_budget(department: str, amount: float) -> str:
    """查询部门预算是否足够。"""
    for row in procurement_data["budgets"]:
        if row["department"] == department:
            available = row["annual_budget"] - row["used_budget"] - row["reserved_budget"]
            return json.dumps(
                {
                    "department": department,
                    "amount": amount,
                    "available_budget": available,
                    "enough": available >= amount,
                    "budget_owner": row["budget_owner"],
                },
                ensure_ascii=False,
            )
    return json.dumps({"department": department, "found": False, "message": "没有找到部门预算。"}, ensure_ascii=False)


def compliance_check(request_json: str, supplier_json: str, budget_json: str) -> str:
    """根据采购申请、供应商和预算信息检查合规风险。"""
    request = json.loads(request_json)
    supplier = json.loads(supplier_json)
    budget = json.loads(budget_json)
    amount = request.get("total_amount", 0)
    issues = []

    if amount > 200000:
        issues.append({"rule_id": "C001", "severity": "high", "message": "单笔超过 200000 元，需要三方比价或说明豁免原因。"})
    if supplier.get("risk_level") == "high" and "全额预付款" in supplier.get("payment_terms", ""):
        issues.append({"rule_id": "C002", "severity": "high", "message": "高风险供应商不得使用全额预付款。"})
    if not budget.get("enough", False):
        issues.append({"rule_id": "C003", "severity": "high", "message": "预算可用余额不足，必须先走预算追加审批。"})
    if "AI" in request.get("item", "") or "核心业务分析平台" in request.get("business_reason", ""):
        issues.append({"rule_id": "C004", "severity": "medium", "message": "涉及 AI 算力或核心业务分析平台，需要信息安全负责人复核部署用途。"})

    return json.dumps({"passed": not any(i["severity"] == "high" for i in issues), "issues": issues}, ensure_ascii=False)


def build_approval_route(amount: float, supplier_risk: str, prepayment_ratio: float = 0.3) -> str:
    """根据金额、供应商风险和预付款比例生成审批路径。"""
    approvers = []

    if amount <= 50000:
        approvers.extend(["直属主管", "部门负责人"])
    elif amount <= 200000:
        approvers.extend(["直属主管", "部门负责人", "财务经理"])
    else:
        approvers.extend(["直属主管", "部门负责人", "财务经理", "分管 VP"])

    if supplier_risk == "high":
        approvers.extend(["法务负责人", "采购负责人"])
    if prepayment_ratio >= 0.3:
        approvers.extend(["财务经理", "资金管理岗"])

    # dict.fromkeys 可以在保持顺序的同时去重。
    route = list(dict.fromkeys(approvers))
    return json.dumps({"approvers": route, "approval_steps": len(route)}, ensure_ascii=False)


print("函数定义完成。下一节先手动跑一遍，不用 Agent。")
```


## 6. 第 1 层：手动跑通完整业务链路

这一节最重要。

先别管 Deep Agents。我们手写调用顺序，看清楚业务本身：

```text
申请文本
-> parse_purchase_request
-> check_inventory
-> check_supplier
-> check_budget
-> compliance_check
-> build_approval_route
```

如果这里看懂了，后面的 Agent 就只是自动帮你执行这条链路。


```python
request_text = "研发平台部申请采购 4 台 AI 推理服务器，优先供应商北辰智能硬件，用于数据分析和自动化测试平台扩容。"

# 1. 把自然语言申请解析成结构化字段。
manual_request = parse_purchase_request(request_text)
manual_request_json = json.dumps(manual_request, ensure_ascii=False)

# 2. 根据申请里的物品和数量查库存。
manual_inventory_json = check_inventory(manual_request["item"], manual_request["quantity"])

# 3. 根据申请里的供应商名称查供应商风险。
manual_supplier_json = check_supplier(manual_request["preferred_supplier"])

# 4. 根据部门和采购金额查预算。
manual_budget_json = check_budget(manual_request["department"], manual_request["total_amount"])

# 5. 合规检查需要综合“申请 + 供应商 + 预算”三个结果。
manual_compliance_json = compliance_check(manual_request_json, manual_supplier_json, manual_budget_json)

# 6. 审批路径需要金额和供应商风险。
manual_supplier = json.loads(manual_supplier_json)
manual_route_json = build_approval_route(
    amount=manual_request["total_amount"],
    supplier_risk=manual_supplier.get("risk_level", "unknown"),
    prepayment_ratio=0.3,
)

print("1. 采购申请")
print(pretty_json(manual_request))
print("\n2. 库存结果")
print(pretty_json(manual_inventory_json))
print("\n3. 供应商结果")
print(pretty_json(manual_supplier_json))
print("\n4. 预算结果")
print(pretty_json(manual_budget_json))
print("\n5. 合规结果")
print(pretty_json(manual_compliance_json))
print("\n6. 审批路径")
print(pretty_json(manual_route_json))
```


## 7. 把手动链路封装成一个“业务评审函数”

上面那串代码有点长，所以这里把它封装成一个函数：`run_procurement_review`。

注意：这仍然不是 Agent，只是普通 Python。

好处是后面可以把它作为一个工具交给 Deep Agent：Agent 只要调用 1 个工具，就能拿到完整评审结果。


```python
def run_procurement_review(request_text: str) -> str:
    """完整采购评审链路。

    输入：用户的一段采购申请文本。
    输出：JSON 字符串，包含申请、库存、供应商、预算、合规、审批路径和最终建议。
    """
    request = parse_purchase_request(request_text)
    request_json = json.dumps(request, ensure_ascii=False)

    inventory_json = check_inventory(request["item"], request["quantity"])
    supplier_json = check_supplier(request["preferred_supplier"])
    budget_json = check_budget(request["department"], request["total_amount"])
    compliance_json = compliance_check(request_json, supplier_json, budget_json)

    supplier = json.loads(supplier_json)
    route_json = build_approval_route(
        amount=request["total_amount"],
        supplier_risk=supplier.get("risk_level", "unknown"),
        prepayment_ratio=0.3,
    )

    inventory = json.loads(inventory_json)
    budget = json.loads(budget_json)
    compliance = json.loads(compliance_json)

    # 这里用确定性规则生成建议，避免完全依赖 LLM 自己猜。
    if not budget.get("enough", False):
        recommendation = "暂缓：预算不足，需要先走预算追加审批。"
    elif any(issue["severity"] == "high" for issue in compliance["issues"]):
        recommendation = "有条件通过：需补充高风险合规材料后再提交审批。"
    elif not inventory.get("enough", False):
        recommendation = "有条件通过：库存不足，需要确认交期或替代方案。"
    else:
        recommendation = "建议通过：预算和合规未发现阻断问题。"

    result = {
        "request": request,
        "inventory": inventory,
        "supplier": supplier,
        "budget": budget,
        "compliance": compliance,
        "approval_route": json.loads(route_json),
        "recommendation": recommendation,
    }
    return json.dumps(result, ensure_ascii=False)


review_json = run_procurement_review(request_text)
print(pretty_json(review_json))
```


## 8. 第 2 层：最小 Deep Agent，只给它 1 个工具

这是最容易理解的 Deep Agent 用法。

我们只给 Agent 一个工具：`run_procurement_review`。

Agent 的工作变成：

```text
读懂用户问题 -> 调用完整评审工具 -> 把 JSON 结果整理成中文结论
```

这样不会一上来就让它自己选择 6 个工具，学习成本低很多。


```python
from deepagents import create_deep_agent


simple_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    system_prompt=(
        "你是采购申请评审助手。"
        "收到采购申请后，必须调用 run_procurement_review 获取真实评审结果。"
        "最后用中文输出：最终建议、关键风险、审批路径。"
    ),
)

simple_result = simple_agent.invoke({"messages": [{"role": "user", "content": request_text}]})
print(simple_result["messages"][-1].content)
```


## 9. 看 Agent 到底做了什么

Agent 不是黑盒。我们把消息和工具调用打印出来。

你重点看两件事：

- 有没有调用 `run_procurement_review`。
- 最终回答是不是基于工具返回的 JSON。


```python
def print_agent_trace(agent_result: dict, max_chars: int = 1600) -> None:
    """打印 Deep Agents 的消息和工具调用轨迹。"""
    for index, message in enumerate(agent_result.get("messages", []), start=1):
        msg_type = message.__class__.__name__
        content = getattr(message, "content", "")
        tool_calls = getattr(message, "tool_calls", None)

        # 只打印关键消息：AI 消息和工具消息。
        if tool_calls or msg_type in {"ToolMessage", "AIMessage"}:
            print("=" * 80)
            print(f"#{index} {msg_type}")
            if tool_calls:
                print("tool_calls:", tool_calls)
            print(str(content)[:max_chars])


print_agent_trace(simple_result)
```


## 10. 第 3 层：进阶，让 Agent 自己编排多个工具

如果你已经看懂第 2 层，再看这一节。

这次不再给 Agent 一个“大工具”，而是给它多个“小工具”：

```text
parse_purchase_request
check_inventory
check_supplier
check_budget
compliance_check
build_approval_route
```

区别：

| 方式 | 优点 | 缺点 |
| --- | --- | --- |
| 1 个大工具 | 稳定、容易理解、适合生产里的确定性流程 | Agent 自主性较低 |
| 多个小工具 | 更能展示 Agent 编排能力 | 更容易漏调、错参，需要看 trace |

学习时推荐先掌握“1 个大工具”，再看“多个小工具”。


```python
multi_tool_agent = create_deep_agent(
    model=llm,
    tools=[
        parse_purchase_request,
        check_inventory,
        check_supplier,
        check_budget,
        compliance_check,
        build_approval_route,
    ],
    system_prompt=(
        "你是采购申请智能评审助手。必须按顺序完成："
        "1. parse_purchase_request 解析申请；"
        "2. check_inventory 查库存；"
        "3. check_supplier 查供应商；"
        "4. check_budget 查预算；"
        "5. compliance_check 查合规；"
        "6. build_approval_route 生成审批路径。"
        "最后用中文输出：是否建议通过、主要风险、审批路径。"
    ),
)

multi_tool_result = multi_tool_agent.invoke({"messages": [{"role": "user", "content": request_text}]})
print(multi_tool_result["messages"][-1].content)
```


## 11. 检查多工具 Agent 的调用轨迹

这一节用来排查：Agent 有没有真的按顺序调用工具。

如果结果不对，优先看这里，而不是直接改 prompt。


```python
print_agent_trace(multi_tool_result)
```


## 12. 第 4 层：子 Agent 分工，作为进阶理解

子 Agent 适合任务真的变复杂的时候。

比如同一笔采购评审，可以分成：

- 采购研究员：看库存、交期、供应商。
- 财务复核员：看预算、审批路径。
- 合规审查员：看合规风险。

这节可以运行，但如果你刚开始学 Deep Agents，可以先跳过。


```python
subagents = [
    {
        "name": "procurement-researcher",
        "description": "负责查询库存、交期、替代方案和供应商风险。",
        "system_prompt": "你是采购研究员。只关注库存、交期、替代方案和供应商风险。",
        "tools": [check_inventory, check_supplier],
    },
    {
        "name": "finance-reviewer",
        "description": "负责检查预算是否足够，并生成审批路径。",
        "system_prompt": "你是财务复核员。只关注预算是否足够、审批路径是否完整。",
        "tools": [check_budget, build_approval_route],
    },
    {
        "name": "compliance-reviewer",
        "description": "负责检查采购申请的合规风险。",
        "system_prompt": "你是合规审查员。只关注合规问题和整改建议。",
        "tools": [compliance_check],
    },
]

subagent_review_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    subagents=subagents,
    system_prompt=(
        "你是采购评审主控 Agent。"
        "优先调用 run_procurement_review 获得完整事实。"
        "必要时可以把采购、财务、合规问题交给子 Agent 复核。"
        "最终输出 Markdown 报告，包含申请摘要、关键风险、审批路径和最终建议。"
    ),
)

subagent_result = subagent_review_agent.invoke({"messages": [{"role": "user", "content": request_text}]})
print(subagent_result["messages"][-1].content)
```


### 12.1 `CompiledSubAgent`：复用已经构建好的 Agent 或 LangGraph

上一节传入的是声明式 `SubAgent`：提供 `system_prompt`、`tools` 等配置，由 Deep Agents 帮我们创建子 Agent。

如果子 Agent 已经通过 LangChain 的 `create_agent()` 或 LangGraph 构建完成，就应该使用 `CompiledSubAgent`，把现成的 `runnable` 直接交给主 Agent。这里的正确名称是 **CompiledSubAgent**，不是 Complicate Subagent。

| 对比项 | 声明式 `SubAgent` | `CompiledSubAgent` |
| --- | --- | --- |
| 传入内容 | 模型、提示词、工具等配置 | 已构建好的 `runnable` |
| 谁负责构建 | Deep Agents | 业务代码自己构建 |
| 适用场景 | 简单的专业分工 | 复用已有 Agent、自定义 StateGraph 或复杂中间件 |

下面把一个已经构建好的财务复核 Agent 注册为 `CompiledSubAgent`：

```python
from langchain.agents import create_agent
from deepagents import CompiledSubAgent

finance_review_graph = create_agent(
    model=llm,
    tools=[check_budget, check_supplier, build_approval_route],
    system_prompt=(
        "你是财务复核员。先查询预算和供应商风险，再生成审批路径。"
        "只返回预算结论、资金风险和审批路径。"
    ),
)

finance_compiled_subagent: CompiledSubAgent = {
    "name": "finance-graph-reviewer",
    "description": "使用已经构建好的财务复核图，独立检查预算、资金风险和审批路径。",
    "runnable": finance_review_graph,
}

compiled_subagent_review_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    subagents=[finance_compiled_subagent],
    system_prompt=(
        "你是采购评审主控 Agent。先调用 run_procurement_review 获取完整事实，"
        "再把财务复核任务委派给 finance-graph-reviewer，最后合并两份结论。"
    ),
)

compiled_subagent_result = compiled_subagent_review_agent.invoke(
    {
        "messages": [
            {
                "role": "user",
                "content": f"请评审以下采购申请，并让财务子 Agent 独立复核：{request_text}",
            }
        ]
    }
)
print(compiled_subagent_result["messages"][-1].content)
```

使用时注意：

- `runnable` 的返回状态必须包含 `messages`，否则主 Agent 无法取得子 Agent 的结果。
- `CompiledSubAgent` 不会继承主 Agent 的 `model`、`tools`、`middleware`、`state_schema` 或 `interrupt_on`；这些能力要在构建 `runnable` 时配置。
- 默认情况下，子 Agent 只看到主 Agent 通过 `task` 工具交给它的任务描述，不会自动获得完整对话。
- 如果返回状态包含非空的 `structured_response`，Deep Agents 会把它序列化后交给主 Agent；否则使用最后一条非空 `AIMessage`。

因此，只有在确实需要复用现成图或自定义状态时才使用 `CompiledSubAgent`；普通角色分工继续使用上一节的声明式写法即可。


### 12.2 `AsyncSubAgent`：把长任务放到远程后台执行

`AsyncSubAgent` 不是“在本进程里并发调用一个子 Agent”，而是通过 LangGraph SDK 在远程 **Agent Protocol** 服务上启动后台任务。主 Agent 会立即拿到 `task_id`，可以继续处理当前对话，之后再查询、追加指令或取消任务。

它适合耗时较长、可以独立运行的研究、批量分析和报告生成任务；几秒钟能完成的调用继续使用同步 `SubAgent` 即可。

```python
from deepagents import AsyncSubAgent, create_deep_agent

remote_researcher: AsyncSubAgent = {
    "name": "remote-procurement-researcher",
    "description": "在后台调查供应商、市场价格和交付风险。",
    "graph_id": "procurement_research_agent",
    "url": "https://your-agent-protocol.example.com",
    # 自托管服务需要认证时再传 headers；不要把密钥写死在代码里。
    # "headers": {"Authorization": f"Bearer {token}"},
}

async_review_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    subagents=[remote_researcher],
    system_prompt=(
        "采购研究预计耗时较长时，使用 remote-procurement-researcher 启动后台任务。"
        "不要持续轮询；只有用户要求查看进度或结果时才检查任务。"
    ),
)

async_result = await async_review_agent.ainvoke(
    {"messages": [{"role": "user", "content": "后台调查供应商风险，并先继续处理采购申请。"}]}
)
print(async_result["messages"][-1].content)
```

配置字段只有几个：

| 字段 | 是否必填 | 作用 |
| --- | --- | --- |
| `name` | 是 | 主 Agent 选择子 Agent 时使用的唯一名称 |
| `description` | 是 | 说明何时应该委派 |
| `graph_id` | 是 | 远程服务中的 graph 名称或 assistant ID |
| `url` | 否 | Agent Protocol 服务地址；省略时使用本地 ASGI transport |
| `headers` | 否 | 自托管服务的认证请求头 |

注册后，Deep Agents 会提供 `start_async_task`、`check_async_task`、`update_async_task`、`cancel_async_task` 和 `list_async_tasks` 工具。任务元数据保存在 state 的 `async_tasks` 中，但真正的执行和线程数据在远程服务端。

注意以下边界：

- 省略 `url` 的本地 ASGI transport 只能从 `ainvoke` 等异步入口使用；同步 `invoke` 必须连接一个可访问的 URL。
- `AsyncSubAgent` 不继承主 Agent 的本地 middleware、skills、state schema 或 HITL 配置；这些能力要配置在远程 graph 内。
- LangGraph Platform / LangSmith Deployment 的认证通常读取环境变量；自托管服务使用 `headers`。
- 不要让模型高频轮询任务。启动后继续做其他工作，只在用户需要结果时检查。


### 12.3 Backends 工具箱：文件存在哪里，命令在哪里执行

Backend 是 Deep Agents 文件工具的存储和执行边界。`ls`、`read_file`、`write_file`、`edit_file`、`glob`、`grep` 都通过 backend 工作；只有实现 `SandboxBackendProtocol` 的 backend 才能真正使用 `execute`。

| Backend | 数据位置与生命周期 | `execute` | 适用场景 |
| --- | --- | --- | --- |
| `StateBackend` | LangGraph state；同一 thread 内有效 | 否 | 默认选择、临时报告、基于 State 的 Skills |
| `StoreBackend` | LangGraph `BaseStore`；可跨 thread 持久化 | 否 | 用户记忆、团队资料、长期 Skills |
| `FilesystemBackend` | 当前主机文件系统 | 否 | 可信的本地开发和 CI 文件操作 |
| `LocalShellBackend` | 当前主机文件系统和本机 shell | 是 | 可信的个人开发环境；**不提供隔离** |
| `CompositeBackend` | 按路径前缀路由到多个 backend | 取决于默认 backend | 临时文件与持久资料混合存储 |
| `ContextHubBackend` | LangSmith Hub agent repo | 否 | 共享、版本化的 Agent 上下文 |
| `LangSmithSandbox` | LangSmith 云沙箱 | 是 | 需要隔离执行的云端任务 |

`StateBackend` 在一次 graph 运行中总是可用；要让文件跨多次调用留在同一 thread，必须配置 checkpointer，并在调用时复用同一个 `thread_id`。

最小用法是显式传入默认的 `StateBackend`：

```python
from deepagents.backends import StateBackend

state_backend_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    backend=StateBackend(),
    system_prompt="把中间结果写到 /work/，最终再汇总。",
)
```

要把临时文件留在 state，同时把长期资料写入 Store，可以按虚拟路径路由：

```python
from deepagents.backends import CompositeBackend, StateBackend, StoreBackend
from langgraph.store.memory import InMemoryStore

store = InMemoryStore()
composite_backend = CompositeBackend(
    default=StateBackend(),
    routes={
        "/memory/": StoreBackend(
            store=store,
            namespace=lambda runtime: ("procurement-assistant", "filesystem"),
        )
    },
)

backend_agent = create_deep_agent(
    model=llm,
    backend=composite_backend,
)
```

这里的 `InMemoryStore` 只用于学习，进程退出后数据仍会丢失。生产环境应替换成实际持久化的 `BaseStore`，并使用用户或租户标识构造 namespace，避免不同用户互相看到文件。

选择顺序可以保持简单：

1. 只是当前任务的中间文件：`StateBackend`。
2. 需要跨会话保存：`StoreBackend`。
3. 可信本地开发需要直接操作文件：`FilesystemBackend`。
4. 需要执行不可信代码：真正隔离的 sandbox backend。
5. 不同目录需要不同生命周期：`CompositeBackend`。


### 12.4 基于 State 的动态 Skills

`skills=[...]` 配置的是**技能目录路径**，`SkillsMiddleware` 会从 backend 中读取每个技能的 `SKILL.md`，先把名称、描述和路径放进系统提示词，真正需要时再由 Agent 读取完整内容。这就是 progressive disclosure。

使用 `StateBackend` 时，可以在每次新会话开始时把不同的 Skill 文件放进输入 state，从而根据用户、租户或任务动态提供技能：

```python
from deepagents.backends import StateBackend

PROCUREMENT_SKILL = """---
name: procurement-review
description: Review enterprise purchase requests for budget, supplier and compliance risks
---

# Procurement Review

1. Parse the request into structured fields.
2. Check inventory, supplier, budget and compliance evidence.
3. Separate blocking risks from recommendations.
4. Never submit an approval without explicit user confirmation.
"""

dynamic_skill_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    backend=StateBackend(),
    skills=["/skills/session/"],
)

dynamic_skill_result = dynamic_skill_agent.invoke(
    {
        "messages": [{"role": "user", "content": request_text}],
        "files": {
            "/skills/session/procurement-review/SKILL.md": {
                "content": PROCUREMENT_SKILL,
                "encoding": "utf-8",
            }
        },
    }
)
```

动态点在于 `files` 的内容由应用在调用前决定，而不是让模型任意加载所有 Skills。例如可以先根据 `tenant_id` 和用户角色在服务层选择允许的 Skill，再组装输入 state。

需要区分三个概念：

| 需求 | 推荐实现 |
| --- | --- |
| 每个新会话使用不同 Skill 集合 | `StateBackend` + 调用时传入不同 `files` |
| 同一用户跨会话复用 Skill | `StoreBackend`，按用户 namespace 隔离 |
| 每一轮都重新计算 Skill 来源 | 自定义 middleware，或为该轮构建新的 Agent；内置 `SkillsMiddleware` 不会自动重载 |

`SkillsMiddleware` 会把解析后的元数据缓存在 `state["skills_metadata"]`，同一 checkpointed session 后续轮次如果已经存在该字段，就跳过重新扫描。因此在同一 thread 中修改 `files` 并不会自动刷新技能目录。最稳妥的做法是：Skill 集合变化时开启新 thread；只有确实需要逐轮热切换时才编写自定义 middleware。

多个 `skills` source 会按顺序加载，同名 Skill 由后面的 source 覆盖前面的 source，适合实现“内置默认 -> 用户 -> 项目”的分层覆盖。所有 backend 路径都使用 POSIX 风格 `/`。


### 12.5 云沙箱、OpenSandbox 与本地执行

“能执行 shell”不等于“有沙箱”。Deep Agents 只要求执行型 backend 实现 `SandboxBackendProtocol`，真正的容器、虚拟机、网络策略、资源限额和销毁机制由 backend 提供者负责。

| 方案 | 隔离位置 | 优点 | 主要边界 |
| --- | --- | --- | --- |
| 云沙箱 | 托管容器或 VM | 隔离、弹性、生命周期 API 完整 | 成本、网络延迟、数据合规 |
| OpenSandbox | 自己的 Docker / Kubernetes | 数据和基础设施可控，无按秒平台绑定 | 要自己运维服务和镜像 |
| `LocalShellBackend` | **没有隔离，直接在主机执行** | 启动最简单、适合个人开发 | 可读取密钥、改写文件、耗尽主机资源 |
| 自定义本地 sandbox | 本机 Docker / VM | 本地可控且有进程隔离 | 需要自己实现或维护 backend 适配 |

Deep Agents 当前直接包含 `LangSmithSandbox`；Daytona、E2B、Modal、Runloop 等通过独立集成包提供。无论选择哪家，只要 backend 实现 `SandboxBackendProtocol`，传给 `create_deep_agent(backend=...)` 后都能获得文件工具和 `execute`。

本地可信开发可以这样使用 `LocalShellBackend`：

```python
from pathlib import Path
from deepagents.backends import LocalShellBackend
from langgraph.checkpoint.memory import MemorySaver

local_backend = LocalShellBackend(
    root_dir=Path.cwd(),
    inherit_env=False,
    env={"PATH": "C:\\Windows\\System32"},
    timeout=60,
)

local_agent = create_deep_agent(
    model=llm,
    backend=local_backend,
    interrupt_on={"execute": True},
    checkpointer=MemorySaver(),
)
```

上面仍然不是安全沙箱。`virtual_mode=True` 只约束文件工具的虚拟路径，shell 命令依然能使用当前用户权限访问主机。不要把 `LocalShellBackend` 放在 Web API、多租户系统或不可信输入前面。

OpenSandbox 是可自托管的隔离运行时，社区适配包的典型结构如下：

```python
# 架构示例：使用前必须先核对版本兼容性。
from opensandbox.sync.sandbox import SandboxSync
from langchain_opensandbox import OpenSandboxSandbox

sandbox = SandboxSync.create("python:3.11-slim")
try:
    sandbox_agent = create_deep_agent(
        model=llm,
        backend=OpenSandboxSandbox(sandbox=sandbox),
    )
    sandbox_result = sandbox_agent.invoke(
        {"messages": [{"role": "user", "content": "创建并运行一个只打印 hello 的 Python 脚本。"}]}
    )
finally:
    sandbox.kill()
```

**当前项目不要直接安装这段示例的适配包。** 截至本文核对时，`langchain-opensandbox 0.1.0` 声明依赖 `deepagents >=0.6.12,<0.7`，而本项目使用 `deepagents 0.7.x`。应等待兼容版本、在独立环境锁定旧版，或基于当前 `BaseSandbox` / `SandboxBackendProtocol` 自行适配；不要为了示例降级主项目依赖。

生产 sandbox 至少要处理：每个 thread/tenant 的实例隔离、CPU/内存/磁盘限制、网络出口策略、密钥注入、命令超时、文件上传下载、审计日志、异常销毁和闲置回收。HITL 可以减少误操作，但不能代替隔离层。


### 12.6 Harness Engineering：设计 Agent 的运行环境

完整专题见：[Harness Engineering：从模型能力到可靠 Agent 系统](./harness_engineering.md)。下面保留与 Deep Agents 直接相关的摘要。

Prompt Engineering 关注“给模型什么指令”；Harness Engineering 关注“模型在什么系统里运行”。Harness 是包围模型的工程外壳，决定上下文如何进入、工具如何暴露、状态如何持久化、危险操作如何拦截，以及结果如何评测。

```text
用户请求
  -> 上下文与记忆
  -> 模型 + Prompt
  -> 工具 / Skills / Subagents
  -> Backend / Sandbox
  -> Checkpoint / HITL / Trace / Evaluation
  -> 可验证结果
```

在 Deep Agents 中可以这样映射：

| Harness 关注点 | Deep Agents 能力 |
| --- | --- |
| 长任务规划与上下文控制 | planning、summarization、filesystem |
| 专业知识按需加载 | Skills、memory |
| 任务分工 | `SubAgent`、`CompiledSubAgent`、`AsyncSubAgent` |
| 状态和恢复 | LangGraph state、checkpointer、store |
| 权限和人工确认 | `permissions`、`interrupt_on`、HITL middleware |
| 隔离执行 | `SandboxBackendProtocol` 及具体 sandbox backend |
| 可观测与质量 | stream、trace、结构化输出、轨迹评测 |

`HarnessProfile` 是 Deep Agents 中针对**模型差异**调整 harness 的 API，不等于 Harness Engineering 的全部。它可以调整 prompt 组装、工具描述、工具可见性、middleware 和默认 general-purpose subagent：

```python
from deepagents import (
    GeneralPurposeSubagentProfile,
    HarnessProfile,
    register_harness_profile,
)

register_harness_profile(
    "openai:gpt-5.4",
    HarnessProfile(
        system_prompt_suffix="输出前检查证据来源和未解决风险。",
        excluded_tools=frozenset({"execute"}),
        general_purpose_subagent=GeneralPurposeSubagentProfile(enabled=False),
    ),
)
```

这套 Profile API 仍是 beta。`excluded_tools` 只影响模型能看到什么，不是安全边界；真正的安全仍要依赖最小权限工具、`permissions`、HITL 和隔离 backend。Profile 的 `extra_middleware` 也不会注入已经编译好的 `CompiledSubAgent` 或远程 `AsyncSubAgent`。

生产 Harness 的最小检查清单：

- 先用确定性代码固定不可违反的业务规则，再让模型处理开放判断。
- 工具只暴露完成任务所需的最小权限；读写和执行权限分开。
- 写操作、付款、审批提交等高风险动作必须有幂等键、审计和人工确认。
- 控制上下文预算：长期记忆、当前 state、检索结果和 Skills 分层加载。
- 每个外部调用都有超时、重试上限和明确失败路径。
- 保存模型调用、工具参数、状态变化和最终证据，敏感字段先脱敏。
- 同时评测最终答案和执行轨迹，包括拒绝路径、超时、恢复和权限绕过。

一个好的 Harness 不追求让 Agent “更自由”，而是让它在可观察、可恢复、权限明确的边界内完成更多任务。


## 13. 虚拟文件系统：让 Agent 写一份报告

Deep Agents 支持虚拟文件系统，适合保存中间文档或最终报告。

这一节让 Agent 把报告写入 `procurement_review_report.md`。


```python
report_agent = create_deep_agent(
    model=llm,
    tools=[run_procurement_review],
    system_prompt=(
        "你是采购评审报告助手。"
        "必须调用 run_procurement_review 获取真实评审结果。"
        "然后把最终 Markdown 报告写入 procurement_review_report.md。"
        "报告必须包含：申请摘要、风险表格、审批路径、最终建议。"
    ),
)

report_result = report_agent.invoke({"messages": [{"role": "user", "content": request_text}]})
print(report_result["messages"][-1].content)
print("\n虚拟文件系统 files:")
print(json.dumps(report_result.get("files", {}), ensure_ascii=False, indent=2)[:3000])
```


## 14. 程序化验收：别只看回答像不像

复杂业务 Agent 要看证据。

下面这个函数检查：

- 是否有最终回答。
- 是否调用了预期工具。
- 是否包含风险和审批路径。
- 是否写入了报告文件。


```python
def inspect_agent_result(agent_result: dict, expected_tools: set[str] | None = None) -> dict:
    """检查 Agent 结果，避免只凭肉眼看回答。"""
    messages = agent_result.get("messages", [])
    final_answer = messages[-1].content if messages else ""

    called_tools = []
    for message in messages:
        for call in getattr(message, "tool_calls", None) or []:
            called_tools.append(call.get("name"))

    expected_tools = expected_tools or set()
    return {
        "has_final_answer": bool(final_answer.strip()),
        "called_tools": called_tools,
        "missing_expected_tools": sorted(expected_tools - set(called_tools)),
        "has_risk_text": "风险" in final_answer or "合规" in final_answer,
        "has_approval_text": "审批" in final_answer,
        "files": list((agent_result.get("files") or {}).keys()),
        "final_answer_preview": final_answer[:500],
    }


print("1 个大工具 Agent 验收:")
pprint(inspect_agent_result(simple_result, {"run_procurement_review"}), width=120)

print("\n多个小工具 Agent 验收:")
pprint(
    inspect_agent_result(
        multi_tool_result,
        {
            "parse_purchase_request",
            "check_inventory",
            "check_supplier",
            "check_budget",
            "compliance_check",
            "build_approval_route",
        },
    ),
    width=120,
)

print("\n报告 Agent 验收:")
pprint(inspect_agent_result(report_result, {"run_procurement_review"}), width=120)
```


## 15. 真实项目里怎么取舍？

建议这样理解：

| 阶段 | 推荐写法 | 原因 |
| --- | --- | --- |
| 刚开始学 | 1 个大工具 | 最容易看懂，稳定 |
| 业务流程固定 | 1 个大工具 + Agent 总结 | 关键判断由代码保证 |
| 流程经常变化 | 多个小工具 | Agent 可以按需组合 |
| 跨部门复杂任务 | 子 Agent | 角色清晰，适合长任务 |
| 要留痕审计 | 虚拟文件系统 + trace | 方便检查和复盘 |

生产建议：

- 真正提交采购单、扣预算、创建审批流这类写操作，不要让 Agent 直接执行。
- 写操作前要让用户确认，后端再用确定性接口执行。
- 工具返回值尽量用 JSON，减少模型误读。
- 每次运行都保存工具调用轨迹，方便排查。

## 16. 接下来学什么？

到这里已经掌握了 Deep Agents 的主要组件，但“组件会用”还不等于“系统可上线”。下一阶段建议学习：

- `State`、`Context`、`Checkpointer`、`Store` 的职责和生命周期。
- 文件权限、Human-in-the-loop，以及它们与执行沙箱的边界。
- Memory、Skills、RAG 的区别和组合方式。
- Structured Output 的模型兼容性与降级策略。
- Summarization、context offloading、prompt caching 和 middleware。
- MCP、多模态文件、代码执行、trace、评测和 Rubric 质量循环。
- 生产环境的多租户隔离、身份、秘密、幂等、恢复和成本治理。

完整路线与毕业项目见：[Deep Agents 进阶学习路线：从会调用工具到可上线](./deep_agents_advanced_learning.md)。

更系统的工程思想见：[Harness Engineering：从模型能力到可靠 Agent 系统](./harness_engineering.md)。

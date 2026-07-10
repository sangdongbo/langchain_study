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

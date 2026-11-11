# PydanticAI：类型驱动 Agent 与分层面试问答

> 用途：中高级 Agent 应用开发复习与面试，以 PydanticAI 为主，补齐必要 Pydantic 基础。核对日期：2026-10-20。
> 版本依据：仓库锁定 `pydantic-ai-slim[openai]==2.55.0`，其 `uv.lock` 中 Pydantic 为 `2.14.1`；浏览器示例另锁定 Pydantic `2.13.5`。这是两个独立项目环境，不能把版本混为一套。
> 文档 API 以本仓库示例与签名为依据。在线官方文档已迁移部分网址并继续更新，新版高级特性不默认视为本仓库已覆盖。

## 阅读导航

- 先建立边界：Pydantic / PydanticAI / 模型 / Provider。
- 再掌握主线：Schema → 工具参数 → 依赖 → 输出 → 业务验收 → 受限重试。
- 最后学习：历史、流式、多 Agent、人工审批、测试与生产可靠性。
- 面试速查：第 13–15 节。
- 高级训练：[第 19–21 节](#advanced-pydantic-ai)，包含校验绕过、调用计数、并发、审批和故障注入。
- 白板演练：[第 22–24 节](#pydantic-ai-whiteboard)，推算 Validator 顺序、审查动态工具、区分业务空值与协议失败。
- 关联：[LangGraph](./01_langgraph.md)、[Deep Agents](./02_deep_agents.md)、[浏览器 Agent](./04_browser_use_playwright.md)、[Agent 思想](./05_agent_engineering.md)。

### 考点检索：按信任边界进入

| 面试关键词 | 精确入口 | 最容易说过头的地方 |
| --- | --- | --- |
| 类型、必填、可空、strict | [Pydantic 基础](#pai-validation) | 注解、解析、校验与事实不是同一层 |
| deps、身份、并发、秘密 | [依赖注入](#pai-deps) | 声明 deps_type 不认证身份、不自动脱敏 |
| Tool / Native / Prompted Output | [结构化输出](#pai-output) | 合法 JSON 不等于有证据的业务结论 |
| UsageLimits、请求数、费用 | [H8 用量口径](#pai-usage) | 响应步、HTTP 尝试、成功工具调用分别统计 |
| deferred、tool_call_id、审批 | [人工审批](#pai-approval) | 展示、批准、实际执行不能混为一步 |
| ValueError、TypeError、ModelRetry | [异常与重试边界](#pai-errors) | 程序 bug 不能靠无限模型重试消化 |
| SecretStr、exclude、校验日志 | [脱敏的覆盖范围](#pai-secrets) | 对象显示遮掩不是全链路数据保护 |
| validator 顺序、动态工具、空结果 | [白板题](#pydantic-ai-whiteboard) | 先预测实际行为，再看参考分析 |

## 1. 名字相近，但不是一个东西

| 名称 | 定位 | 最常见职责 |
| --- | --- | --- |
| Pydantic | Python 数据建模与运行时校验库 | 字段约束、转换、序列化、JSON Schema |
| PydanticAI | 构建 Agent 的 Python 框架 | 模型调用、工具循环、依赖、输出校验和运行管理 |
| LLM | 模型服务本身 | 理解输入、生成文本或工具调用 |
| Model | 框架对模型调用方式的抽象 | 请求 / 响应适配 |
| Provider | 提供模型访问配置与客户端的服务层抽象 | 服务地址、认证、SDK 接入 |
| `BaseModel` | Pydantic 的数据结构基类 | 不是 LLM 抽象基类 |

安装包 `pydantic-ai-slim[openai]`，Python 导入通常是 `pydantic_ai`。`openai` extra 在本仓库也用于兼容接口，并不表示只能选择某一家模型。

“类型驱动”指把业务输入、工具与输出的契约表达进 Python 类型和 schema，减少无结构字符串在各层传递。它不是“模型像编译器一样永远不会犯错”。

<a id="pai-validation"></a>

## 2. Python 类型注解与 Pydantic 校验

普通函数 `def f(amount: int)` 的注解默认不阻止传入字符串。静态检查器可提前发现部分问题，运行时仍需要校验边界。

Pydantic 模型构造或 `model_validate` 会对输入执行解析与约束检查。默认模式可进行合理转换，如数字字符串转数字；严格模式会减少转换，但不同类型及 Python / JSON 输入路径的严格规则仍有差异。

### 2.1 常用建模能力

- `BaseModel`：定义对象 schema。
- `Field`：数值范围、字符串长度、默认值、描述等。
- `Annotated`：为类型附加可组合约束。
- `Literal` / Enum：有限合法值。
- 嵌套模型与集合：表达复杂结构。
- 判别联合：通过明确标签区分 success / failure 等不同结构。
- `ConfigDict(extra="forbid")`：拒绝未声明字段，避免静默忽略模型多编的属性。
- `field_validator`：字段级规则。
- `model_validator`：跨字段不变量。

### 2.2 必填、可空、默认值

在 Pydantic v2 的常规模型声明中，`note: str | None` 表示允许字符串或 None，但没有默认值时仍是必填字段；“允许传 None”不等于“允许省略”。
`note: str | None = None` 才明确提供缺省值。

可变默认值建议用 `Field(default_factory=list)` 或 dataclass 的 `field(default_factory=list)`，清楚表达每个实例独立创建容器。

字段描述帮助模型理解含义，不执行规则；“金额必须非负”要写成 `Field(ge=0)`，不能只写在 description。

### 2.3 序列化、Schema 与输入解析

| API | 做什么 | 注意 |
| --- | --- | --- |
| `model_validate` | 从 Python 输入校验 | 不保证任意已存在实例重新完整校验 |
| `model_validate_json` | 从 JSON 文本校验 | 与 Python 输入模式的转换行为可能不同 |
| `model_dump` | 转成 Python 字典 | 可保留 Decimal 等 Python 对象 |
| `model_dump(mode="json")` | 转成 JSON 兼容值 | 适合继续交给 JSON 编码器 |
| `model_dump_json` | 直接得到 JSON 字符串 | 不要再套一层 JSON 编码造成双重编码 |
| `model_json_schema` | 生成结构说明 | 不执行实际业务 |
| `model_copy(update=...)` | 复制并更新字段 | update 数据不会自动按完整输入重新校验 |
| `model_construct` | 不经过常规校验构造 | 不用于不可信模型输出 |

赋值校验、默认值校验、实例重校验需要看配置。创建时合法，不代表以后任意修改仍合法；`frozen` 也不等于所有嵌套容器深度不可变。

## 3. 一个纯 Pydantic 的完整例子

仅使用固定虚构数据，不涉及模型、网络、数据库。本次整理只做语法检查，不执行片段。

```python
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Purchase(BaseModel):
    # 拒绝多余字段，避免“审批人”等未授权信息被悄悄接收。
    model_config = ConfigDict(extra="forbid")
    quantity: int = Field(gt=0)
    unit_price: Decimal = Field(gt=0, allow_inf_nan=False)
    total: Decimal = Field(gt=0, allow_inf_nan=False)
    note: str | None = None

    @model_validator(mode="after")
    def verify_total(self) -> "Purchase":
        # 字段类型合法仍可能金额矛盾，需要跨字段检查。
        if self.total != self.quantity * self.unit_price:
            raise ValueError("总额与数量、单价不一致")
        return self


purchase = Purchase.model_validate(
    {"quantity": 4, "unit_price": "68000.00", "total": "272000.00"}
)
assert purchase.total == Decimal("272000.00")
assert Purchase.model_validate_json(purchase.model_dump_json()) == purchase
```

这只能证明三个字段之间一致，不能证明真实世界确实买了四台、价格来源可靠或当前用户有采购权限。

金额进一步需要明确币种、最小单位、精度与舍入规则。整数分适合固定两位小数金额；Decimal 适合显式十进制计算，两者都优于直接用 float 推算财务金额。

## 4. PydanticAI 的执行模型

一份 Agent 配置包含模型、指令、工具、依赖类型和输出类型。创建 `Agent(...)` 不等于发起模型请求；`run`、`run_sync` 等入口才启动任务。

典型一次 run：

```text
可信调用方提供 prompt、deps、历史和预算
  → 模型获得消息与工具 schema
  → 模型提出工具调用
  → 框架校验参数，代码检查权限并执行
  → 工具结果回到模型，可能继续循环
  → 输出类型校验与业务 validator
  → 返回 result.output 或明确失败 / 待审批请求
```

一次 run 可以包含多次模型 request、多次工具调用及多个重试。不要把 run 次数当请求数或费用。

同步入口便于普通脚本；已有事件循环的 Web 服务 / Notebook 应使用异步入口，避免在运行中的 loop 里再调用 `run_sync` 或 `asyncio.run`。

## 5. 工具：类型、文档与真实能力边界

`@agent.tool_plain` 用于不接收 RunContext 的工具；`@agent.tool` 可通过 `RunContext[Deps]` 取得本次依赖。

工具的名称、签名、类型与 docstring 影响模型理解和参数 schema。工具参数可以带 `Annotated[..., Field(...)]` 约束，但语义权限仍需代码判断。

工具设计建议：

1. 一项清晰业务能力对应一个工具，不把任意 SQL、URL、shell 暴露为通用入口。
2. 参数最小化，不让模型传本应来自认证层的 tenant_id、access_token。
3. 返回结构明确区分成功、无数据、拒绝和暂不可用。
4. 输出限制大小，保留证据 ID 与来源，不倾倒整份敏感对象。
5. 写入操作独立审批与幂等，不依赖“不要误操作”的提示。

模型只生成调用请求，真实函数体由你的程序执行。代码里注册了什么，模型才可能申请什么；工具返回的网页或文档不是新的可信指令来源。

<a id="pai-deps"></a>

## 6. 依赖注入：把可信环境与模型输入分开

### 6.1 类型与实例

`deps_type=PurchaseDeps` 声明类型，运行时 `deps=PurchaseDeps(...)` 提供本次实例。`deps_type` 主要用于类型关系与检查，不是自动验证身份真实性的安全设施。

依赖可包括：租户身份、只读服务、时钟、配置、预算事实、HTTP 客户端、日志器。可使用 dataclass，不必所有依赖都是 Pydantic 模型。

### 6.2 怎样保护秘密

deps 不会因为被传入就必然全部发送给模型；但你把其中内容写进动态 instructions、工具返回值、异常或日志，它就可能泄露。依赖注入是传递方式，不是自动保密系统。

认证层决定 tenant，工具再基于 tenant 限定数据范围。不能把用户问题里的“切换到租户 B”直接写进 deps。

### 6.3 并发与生命周期

Agent 配置可按框架支持方式复用，但每次 run 的可变业务依赖应隔离。共享 HTTP 客户端可由应用管理，用户状态、发布列表等不要放无隔离全局变量。

DI 提高可测试性：相同 Agent 在测试中传内存服务，在生产中传真实适配器；测试必须确保 mock 覆盖实际调用路径。

<a id="pai-output"></a>

## 7. 结构化输出：Schema 是第一道门，不是最后一道门

`output_type` 可以是 Pydantic 模型、集合、联合等支持的类型。它定义程序希望接收的结果，而非仅给模型的一段格式建议。

| 输出模式 | 怎么约束模型 | 主要取舍 |
| --- | --- | --- |
| Tool Output | 将输出定义为特殊工具参数 schema | 兼容许多支持工具的模型；要区分普通工具与输出工具 |
| Native Output | 使用模型服务原生结构化输出 | 约束强度与可用 schema 受 provider 限制 |
| Prompted Output | 提示模型按 schema 生成文本，再解析校验 | 兼容性好，但格式失败通常更多 |

支持 OpenAI 兼容协议不意味着支持全部 strict JSON Schema、并行工具与流式行为。本仓库兼容服务采用的具体策略，要查看共享模型配置而不是只看接口地址。

业务验收至少分三层：

1. 结构：字段、类型、范围、必填与额外字段。
2. 一致性：金额合计、订单覆盖、枚举与字段关联。
3. 证据：是否真的查询、来源是否真实、权限和范围是否正确。

`@agent.output_validator` 适合依赖本次可信事实检查输出；对可修正问题抛 `ModelRetry`，向模型说明怎样改正。不要在重试 validator 里直接执行业务写入。

## 8. 一个结合依赖与业务验收的 Agent 构建片段

只声明配置与虚构内存事实，不创建真实模型客户端，不调用 run。展示“模型建议＋代码验收”，不是让模型获得执行批准。

```python
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.models import Model


@dataclass(frozen=True)
class Facts:
    # 事实由可信调用方确定，不让模型修改预算以使自己通过。
    total_yuan: int
    budget_yuan: int


class Advice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    decision: Literal["approve", "reject"]
    gap_yuan: int = Field(ge=0)
    reason: str = Field(min_length=1)


def build_agent(model: Model) -> Agent[Facts, Advice]:
    agent = Agent(model, deps_type=Facts, output_type=Advice, retries=2)

    @agent.instructions
    def instructions(ctx: RunContext[Facts]) -> str:
        # 只提供本次任务需要的金额，不把整个依赖对象序列化给模型。
        return (
            f"采购总额 {ctx.deps.total_yuan} 元，预算 {ctx.deps.budget_yuan} 元。"
            "超预算必须 reject，否则 approve；这只是评审建议，不执行采购。"
        )

    @agent.output_validator
    def validate(ctx: RunContext[Facts], output: Advice) -> Advice:
        gap = max(0, ctx.deps.total_yuan - ctx.deps.budget_yuan)
        expected = "reject" if gap else "approve"
        if output.gap_yuan != gap or output.decision != expected:
            # 反馈可修正事实；重试还应受整个运行的 UsageLimits 约束。
            raise ModelRetry(f"结论应为 {expected}，预算缺口应为 {gap} 元。")
        return output

    return agent
```

说明：reason 是自由文本，本例未逐句证明它真实；金额和枚举通过验收，不等于整段解释已完成事实审计。

## 9. 重试、用量与错误分类

### 9.1 三种重试不要混在一起

- Provider / HTTP 重试：处理网络或限流等基础故障。
- 工具参数或执行纠错：模型修正调用参数后再尝试。
- 最终输出纠错：类型或业务 validator 拒绝后重新生成。

三层叠加会扩大时间与费用；`retries=2` 不是“整个系统任何动作总共最多两次”。具体计数受本版本工具、输出分类与配置影响。

### 9.2 用量限制

本仓库通过 `UsageLimits(request_limit=..., tool_calls_limit=...)` 限制运行。严格说，2.55.0 的前者限制 Agent 循环采纳的模型响应步数，后者限制成功工具调用，不等于所有底层 HTTP 尝试和工具尝试的总数；详细计数见 H8。还应设置单次请求超时、总任务期限与可用的 token 预算。

`RunUsage` 可显式在父子 Agent 或审批恢复阶段共享，防止每个阶段重开预算。Token 上限也不是绝对实时账单锁，需考虑请求前未知输出、provider 内重试及计费口径。

### 9.3 错误怎么处理

| 错误 | 推荐策略 |
| --- | --- |
| 部门名称拼错、输出金额与事实矛盾 | 明确可修正反馈，有限 ModelRetry |
| 权限不足、禁止跨租户 | 终止 / 人工处理，不让模型试其他身份 |
| 临时网络错误、429 | 有限退避并遵守服务端等待提示 |
| 真实写入结果不确定 | 先查询对账，不能盲目重复执行 |
| 业务前置条件失效 | 重新采集事实或重新审批 |
| 预算耗尽 | 明确部分完成或失败，不能默默升级模型 / 扩大预算 |

## 10. 历史与流式：管理运行之间的边界

### 10.1 消息历史

`result.all_messages()` 包含该 run 使用的整体历史；`new_messages()` 用于取得本轮新增。续聊时通过 `message_history` 明确传入，不是框架默认永久保存所有会话。

如果数据库已有旧历史，又把 all_messages 全部再次追加，就可能重复。工具调用与返回需要完整配对，不能按字符长度随意切断历史。

`instructions` 与历史里的 `system_prompt` 语义有区别；动态指令应从本次依赖产生。历史保留策略、摘要、跨用户隔离和持久化由应用负责。

### 10.2 流式输出

`run_stream` 支持流式消费；`stream_text(delta=True)` 返回新增片段，累计模式返回当前累计文本。把累计模式每次都追加会出现重复内容。

流式结构化结果可能是尚不完整的对象，不应据其触发写入。即使框架提供了部分解析或校验，也要以最终完整结果和业务验收为准。

运行失败、消费者取消或连接断开时要清理流资源。已经执行成功的外部工具不会因为前端断流自动回滚。

## 11. 多 Agent 与人工审批

### 11.1 多 Agent 的几种组织

- 工具委派：父工具中调用 child.run，拿到类型化结果后返回给父。
- 应用层 handoff：代码决定当前由哪个 Agent 接管。
- 图编排：阶段、路由和恢复由外部图管理。

父子可以使用相同模型，角色差异来自指令、工具、输入和输出。父历史不应自动全部转给子级；传最小事实与约束即可。

仓库委派专题显式传 `deps`、`usage`、`usage_limits`，使父子共享可信事实与预算。自然语言里的“专家说了”不能替代子输出业务校验。

<a id="pai-approval"></a>

### 11.2 Deferred Tools

`requires_approval=True` 的工具可在真正执行前产生待审批请求，输出包含 `DeferredToolRequests`。调用方收集决定后，用完整历史和 `DeferredToolResults` 继续。

`ToolApproved` / `ToolDenied` 必须对应原 `tool_call_id`。修改参数通过明确 override，重新校验后执行；一句“同意”不是框架审批对象。

这是一次结束后再启动跟进 run 的恢复协议，不是跨进程保存 Python 调用栈；生产持久化、审批身份、过期和防重由应用实现。

工具批准后已经写入，即使后续模型汇总失败，写入也不会自动撤销。拒绝后模型再次提出的新动作，需要新的审批，不继承旧批准。

## 12. 测试：类型正确与模型正确分开验证

| 测试层 | 做什么 | 能证明什么 |
| --- | --- | --- |
| Pydantic 单元检查 | 合法 / 非法字段、跨字段关系、序列化 | 数据规则实现 |
| `TestModel` | 用 schema 产生测试行为 | 大部分应用接口可接通 |
| `FunctionModel` | 控制具体模型响应、错误与工具序列 | 业务分支和纠错流程 |
| 依赖替换 | 内存服务、固定时钟、虚构用户 | 无需接触真实外部系统 |
| 少量真实模型评估 | 多任务、多次运行、统计指标 | 模型实际规划与工具选择能力 |

`TestModel` 不是小模型，也不理解用户意图；它可能默认尝试所有工具。若注册的是生产写入工具，不先替换依赖或工具，就可能真的产生副作用。

`models.ALLOW_MODEL_REQUESTS=False` 可阻止意外真实模型请求，但不会自动阻止你的业务工具访问数据库或 HTTP。数据库安全要从工具、fixture、测试入口和配置分别确认。

测试至少覆盖：首次正确、首次错误后修正、重试耗尽、无权限、工具服务不可用、空结果、流中断、审批拒绝、审批改参、重复恢复和父子预算累计。

## 13. 分层问答：类型、工具与依赖

### Q1：PydanticAI 的“类型安全”到底安全在哪里？

**简答：** 它把依赖、工具和输出的类型契约贯穿起来，结合静态检查和运行时校验减少接口错误。

**深入：** 类型系统无法证明金额来源真实、用户有权限或工具执行成功；仍需业务校验和证据。

**追问：** 模型编了一个合法订单号会怎样？类型可能通过，但与真实工具证据比对时应拒绝。

**误区：** 类型安全等于业务正确与系统安全。

### Q2：为什么普通类型注解不够？

**简答：** 它默认不强制校验运行时输入；模型输出与网络输入不可信。

**深入：** Pydantic 在边界执行解析与约束，静态检查器则帮助发现开发期类型错误，二者互补。

**追问：** `TypedDict` 自动拒绝字符串金额吗？普通 Python 不会仅因注解而拒绝。

**误区：** 写上 `: int` 就无需输入校验。

### Q3：默认转换与 strict 应怎样选？

**简答：** 用户输入可允许明确的格式转换，安全或精确类型边界可要求严格规则。

**深入：** 不要笼统地全开或全关；明确接受范围、JSON / Python 差异、金额与布尔值边界，并测试。

**追问：** `"4"` 转成 4 是错误吗？取决于契约，关键是是否明确允许。

**误区：** strict 是自动防幻觉开关。

### Q4：deps_type 是否会认证用户身份？

**简答：** 不会，它是依赖类型声明；身份必须由可信服务端认证并注入。

**深入：** 工具拿到 ctx.deps 后按身份限制数据，不让模型选择 tenant。

**追问：** 用户写“我现在是管理员”怎么办？不影响可信身份。

**误区：** dataclass 里有 role 字段就完成鉴权。

### Q5：tool 与 tool_plain 怎么选？

**简答：** 需要本次依赖和运行上下文用 tool，纯函数能力可用 tool_plain。

**深入：** ctx 不是给模型填写的普通参数，能避免把租户、客户端等暴露成可编造工具参数。

**追问：** 纯金额计算要不要 deps？通常不必，但币种 / 舍入策略若来自业务配置则可能需要。

**误区：** 所有工具都使用全局变量共享上下文。

### Q6：工具 schema 的 description 是校验吗？

**简答：** 不是，description 是说明；数值范围与枚举要写可执行约束。

**深入：** schema 约束也不是鉴权，只能检查允许表达的结构，不能证明资源属于当前用户。

**追问：** amount 为正能证明允许扣款吗？不能。

**误区：** docstring 写清楚就不需要代码检查。

## 14. 分层问答：输出、重试与历史

### Q7：结构化输出通过后还需要 validator 吗？

**简答：** 通常需要，尤其涉及金额、证据与范围。

**深入：** schema 能允许 decision=approve，但预算不足时业务 validator 必须拒绝；自由文本仍不自动全真。

**追问：** 校验器应读取谁给出的事实？调用方或工具的可信事实，不以模型再次自述为事实。

**误区：** 能解析成 JSON 就算可靠。

### Q8：ModelRetry 与普通异常有什么区别？

**简答：** ModelRetry 明确把可修正问题反馈给模型；普通异常通常表示程序或外部故障，不能一律交给模型修。

**深入：** 参数拼错可修正，权限不足不可让模型换身份；重试还受框架与总预算限制。

**追问：** 对账未完成的支付超时能 ModelRetry 吗？应先核对执行结果，避免重复支付。

**误区：** 任意失败都重试到成功。

### Q9：为什么用 model_copy 改字段后数据不合法？

**简答：** update 不是重新完整校验输入的入口。

**深入：** 不可信更新应走 model_validate 等边界，必要时重新检查跨字段不变量；实例赋值规则也看配置。

**追问：** frozen 能防止嵌套列表被修改吗？不代表深度冻结。

**误区：** 所有 Pydantic 方法都自动做相同校验。

### Q10：all_messages 与 new_messages 的实际区别？

**简答：** 前者用于取得整个 run 的历史视图，后者只取得本轮新增内容，保存策略应与已有历史对齐。

**深入：** 续聊与持久化不能两头同时重复拼接，工具调用对也要完整。

**追问：** 为什么 token 越聊越快膨胀？先检查是否重复追加了旧历史，再检查摘要策略。

**误区：** 每次把 all_messages 追加到旧历史末尾。

### Q11：流式结构化对象能边生成边执行吗？

**简答：** 不应直接触发副作用，部分对象还可能缺字段、改字段或最终失败。

**深入：** 流式用于展示进展，执行边界应等待完整验收与必要审批。

**追问：** 模型先输出 approve 后改 reject 呢？所以中间文本不能作为执行许可。

**误区：** 局部解析成功就拥有最终语义。

### Q12：输出模式该如何选择？

**简答：** 根据模型实际能力、schema 支持和错误成本选择，而不是认为原生严格输出总适用。

**深入：** Tool Output 常见，Native 依赖 provider，Prompted 更宽兼容；无论哪种都要本地校验与业务验收。

**追问：** OpenAI 兼容端点是否支持全部模式？不能假设，需明确测试。

**误区：** 协议兼容等于模型行为一致。

## 15. 分层问答：审批、测试与选型

### Q13：为什么审批要 tool_call_id？

**简答：** 使批准绑定具体调用，避免将一条“同意”误用到其他动作。

**深入：** 还需绑定参数版本、审批人、时效和权限，改参要重新校验。

**追问：** 相同工具名称的两笔发布能共用批准吗？不能只凭名称复用。

**误区：** 一次同意后自动批准整段会话。

### Q14：父子 Agent 的费用如何限制？

**简答：** 显式共享用量与限制，并对每类子任务设并发、时间和输出边界。

**深入：** 仅限制父请求而让每个 child 另建预算，会使总调用量远超预期。

**追问：** 审批恢复后请求数能清零吗？不应因此绕过同一业务任务总预算。

**误区：** 子 Agent 费用不属于父任务。

### Q15：TestModel 是否等于真实模型评估？

**简答：** 不是，它是程序化测试替身，不理解真实用户意图。

**深入：** 用它测试类型和工具接口，用 FunctionModel 控制特定路径，再用真实模型数据集评估规划能力。

**追问：** 设置禁止模型请求能避免业务写入吗？不能，还要 mock 工具和依赖。

**误区：** 测试无 Key 就一定不访问生产系统。

### Q16：PydanticAI 与 LangGraph 怎样选？

**简答：** 以前者组织类型化单 / 多 Agent 接口，以后者处理需要显式图控制和恢复的复杂流程，也可组合。

**深入：** 选择依据是任务形态、团队经验、运行基础设施与恢复需求，不是框架热度。

**追问：** 有类型化输出就无需工作流吗？类型解决数据契约，工作流解决执行顺序与生命周期。

**误区：** 将二者视作同一层的完全替代品。

## 16. 仓库案例与项目讲述

- [PydanticAI 总览](../pydantic_ai_examples/README.md)
- [基础 Agent](../pydantic_ai_examples/examples/01_basic_agent/README.md)
- [结构化输出](../pydantic_ai_examples/examples/02_structured_output/README.md)
- [工具与依赖](../pydantic_ai_examples/examples/03_tools_and_deps/README.md)
- [输出校验与重试](../pydantic_ai_examples/examples/04_validation_retry/README.md)
- [消息历史](../pydantic_ai_examples/examples/05_message_history/README.md)
- [流式](../pydantic_ai_examples/examples/06_streaming/README.md)
- [父子委派](../pydantic_ai_examples/examples/07_agent_delegation/README.md)
- [人工审批](../pydantic_ai_examples/examples/08_human_approval/README.md)

项目回答可以说：“我将认证上下文放 deps，把模型输入与真实身份隔离；用 schema 校验结构，用 output_validator 核对预算；可修正问题有限重试，权限问题终止；审批结果绑定 tool_call_id，父子和恢复阶段共用预算。”

不要说：“因为用了 Pydantic，模型不会幻觉，工具一定安全，审批一定只执行一次。”

## 17. 一分钟口述模板

“PydanticAI 的价值是让 Agent 的依赖、工具和最终输出围绕 Python 类型契约组织。我会先用 Pydantic 表达结构与约束，再通过 RunContext 注入可信身份和服务，不让模型生成租户或秘密。模型输出先过 schema，再与工具事实做业务验收；可以纠正的错误使用有限 ModelRetry，权限或未知写入结果走终止与对账。消息历史、父子用量、审批恢复都显式管理。类型提高可维护性，但不能代替事实校验、鉴权、幂等和真实模型评估。”

## 18. 官方依据与版本提醒

- [Pydantic Models](https://pydantic.dev/docs/validation/latest/concepts/models/)
- [Pydantic Validators](https://pydantic.dev/docs/validation/latest/concepts/validators/)
- [Pydantic v2 Migration：校验异常与可空字段](https://pydantic.dev/docs/validation/latest/get-started/migration/)
- [Pydantic Types：Secret 类型与明文访问](https://pydantic.dev/docs/validation/latest/api/pydantic/types/)
- [PydanticAI Agent](https://pydantic.dev/docs/ai/core-concepts/agent/)
- [Dependencies](https://pydantic.dev/docs/ai/core-concepts/dependencies/)
- [Output](https://pydantic.dev/docs/ai/core-concepts/output/)
- [Function Tools](https://pydantic.dev/docs/ai/tools-toolsets/tools/)
- [Deferred Tools](https://pydantic.dev/docs/ai/tools-toolsets/deferred-tools/)
- [Testing](https://pydantic.dev/docs/ai/guides/testing/)
- [Multi-Agent Patterns](https://pydantic.dev/docs/ai/guides/multi-agent-applications/)

旧教程中的 `result_type`、`result.data` 等名称可能不适用于本项目；本仓库使用 `output_type`、`result.output`。查看在线新功能时，先确认 2.55.0 是否具有对应 API，不以站点最新导航当作本环境功能清单。

<a id="advanced-pydantic-ai"></a>

## 19. 高级追问：类型、运行时、事实与权限的四道边界

不要把“类型驱动”简化成“多写几个 BaseModel”。高级问题关心数据经过了哪条入口、是否重新校验、校验依据来自哪里，以及失败反馈会引发什么执行。

速查：类型与校验入口看 H1–H4；输出模式与 validator 看 H5–H6；依赖与计费看 H7–H8；历史、审批看 H9–H10；并发与测试看 H11–H12。第 20 节练习把这些机制串成业务方案。

### H1：类型检查、JSON Schema、运行时校验、事实验收有什么区别？

**第一问：** `Agent[Deps, Advice]` 能保证什么？它帮助静态工具理解 deps 与返回类型的关系；实际不可信输入仍要经过框架 / Pydantic 的运行时解析，静态注解不会给任意 Python 对象自动验真。

**追问一：JSON Schema 给模型后，本地还需校验吗？** 需要。Provider 对 schema 支持有子集限制，兼容端点行为不一，还可能拒答、截断或返回错误。Schema 是契约表达，不是跨所有模型通用的执行证明。

**追问二：字段全合法，为什么还能错？** `order_id="DEMO-100"` 和正数金额都可满足 schema，但编号可能不存在、金额可能过期、对象可能属于其他租户。事实需要可信证据，访问需要鉴权。

**追问三：跨字段一致就代表真实？** 不代表。模型编出数量 2、单价 100、总额 200，内部完全一致，却可能没有对应业务。完整边界是：结构合法→内部一致→来源支持→当前动作获授权。

### H2：strict=True 为什么对 Python 和 JSON 可能表现不同？

**第一问：** 严格模式是否禁止所有字符串转换？不能一概而论。JSON 没有原生 date、UUID 等 Python 类型，严格 JSON 校验在部分类型上仍接受规范字符串；Python 输入路径可以更严格。

**追问一：那“用 strict 防幻觉”错在哪里？** strict 主要约束类型转换，不判断模型是否有证据。它能拒绝某些错误表达，不能证明编号、日期或金额是真实值。

**追问二：字符串金额到底该不该接受？** 由外部契约决定。若页面数据天然是字符串，应有明确的格式解析与 Decimal 规则；不要先宽松转 float 再声称 strict 已保证财务精度。

**追问三：默认值和已有实例也严格校验吗？** 分别看 validate_default、revalidate_instances 等配置。strict 不是覆盖所有生命周期入口的统一开关。

**测试矩阵：** 同一类型分别测 Python 输入、JSON 输入、默认值、已有实例、复制更新、嵌套赋值。不能只测 `Model(x="1")` 一个入口。

### H3：对象创建时合法，为什么十分钟后再传入却不合法？

**第一问：** 普通赋值会重新验吗？默认不应这样假设；validate_assignment 针对属性赋值，嵌套容器原地修改未必经过它。

**追问一：冻结模型能解决吗？** frozen 不等于深度不可变；里面的 list / dict 仍有其自身可变性。需要不可变数据结构或在边界重新构建、校验，而不是只加一个配置。

**追问二：model_validate(existing_model) 一定重验吗？** 取决于该模型的实例重校验配置。把已经被不安全修改的实例重新传入，并不天然触发完整字段校验。

**追问三：model_copy(update=...) 安全吗？** update 被当作可信更新，不自动做完整输入校验。对不可信修改，可从明确的规范字段字典重新构造模型，再检查跨字段规则；处理 alias 时还要按实际输入契约选用字段名。

纯内存示意，本次只检查语法，不执行：

```python
from pydantic import BaseModel, ConfigDict, Field, ValidationError


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)
    amount: int = Field(gt=0)
    labels: list[str] = Field(default_factory=list)


draft = Draft(amount=100)
# model_copy 的 update 不经过常规输入校验，不能接收外部未经校验的修改。
unsafe = draft.model_copy(update={"amount": -1})
assert unsafe.amount == -1

# 从规范字段数据重建，才在这个简单 schema 上重新执行约束。
try:
    Draft.model_validate(unsafe.model_dump())
except ValidationError:
    rejected = True
else:
    rejected = False
assert rejected

# 属性赋值校验不会拦截容器内部所有变动，避免把 frozen / assignment 理解成深冻结。
draft.labels.append("演示标签")
assert draft.labels == ["演示标签"]
```

生产建模还需决定是否允许模型原地修改、怎样处理嵌套模型与实例重验；不是在所有位置复制字典就能解决全部问题。

### H4：成功 / 失败都放一个对象里，为什么容易出现“不可能状态”？

**第一问：** `{ok: bool, data: optional, error: optional}` 有什么问题？它可能表达 ok=true 但无 data、失败却附有成功数据等无意义组合。可用判别联合，把每种状态所需字段放在各自模型。

**追问一：普通 Union 就行吗？** 在形状相似、存在宽松转换时可能不够清晰。用 `kind: Literal[...]` 作为 discriminator，可更明确地选择分支；每个分支仍需自己约束 extra、字段关系和语义。

**追问二：外层 extra=forbid，会传给所有嵌套模型吗？** 不要假定配置跨独立模型递归继承。嵌套模型应显式继承共同基类或配置，并有自己的测试。

**追问三：输出 union 里加 str 兜底好吗？** 取决于任务。它方便自由文本，但也可能使模型用一段话绕开必须的结构化业务验收；关键任务应明确何时允许解释、何时必须返回可验收对象。

### H5：Tool、Native、Prompted 三种输出，遇到复杂 schema 怎样选？

**第一问：** Native 是否最强？它能利用 provider 的原生约束，但有模型与 schema 支持限制，不是普遍更好。Tool Output 将最终对象作为特殊输出工具参数；Prompted Output 依赖文本生成后解析，各有失败模式。

**追问一：模型支持工具就一定支持结构化输出工具吗？** 要验证实际服务能力，包括嵌套对象、联合、必填 / nullable、additionalProperties 与流式。接口名相同不代表语义相同。

**追问二：普通工具调用和最终输出同时返回呢？** 是否执行剩余工具、何时结束，受当前版本终止策略与流式入口影响。不可把“响应里有一份合法对象”直接解释为所有必需工具已完成；业务 validator 应核对证据，不依赖模型输出顺序。

**追问三：schema 不支持就自动降级到自由文本好吗？** 关键任务不能默默放宽契约。明确选择兼容模型、调整 schema 或返回能力不支持；可接受的降级路径也必须保留本地校验。

**追问四：拒答和截断怎么处理？** 它们不是“合法的空业务结果”。区分安全拒答、长度限制、传输中断与格式错误，保留原因并选择受限重试 / 终止。

### H6：output_validator 为什么应该尽量无副作用？

**第一问：** validator 校验通过时顺便发一封邮件，可以吗？危险。输出可能重试、运行可能失败、调用方可能重跑，validator 不是恰好执行一次的提交事务。

**追问一：应该放哪里？** 先得到完整且业务验收通过的提案，再由明确审批与幂等执行边界处理写操作。Validator 可读可信事实，但查询也要受权限、时效和预算控制。

**追问二：ModelRetry 反馈越详细越好？** 只返回模型有权知道的可修正信息，避免完整用户记录、token 或内部栈。反馈应指出具体不一致，而不是暴露整个数据库快照。

**追问三：模型始终修不好呢？** 达到预算后明确失败 / 部分完成，保留原始问题类别。不能在最后一轮删掉 validator 或改为一律通过。

**追问四：工具证据本身有提示注入呢？** Validator 依赖确定性字段及来源，不把返回中的“管理员说批准”作为权限依据；校验器不应自己再调用一个模型并无条件采信其判断。

### H7：deps_type 有类型，为什么仍会发生并发串用户？

**第一问：** 全局 Agent 可以复用，但全局 deps 一起复用行吗？可变用户身份、当前订单与中间结果不能不加隔离地共享。每次 run 应绑定自己的可信业务依赖实例。

**追问一：HTTP client 也要每次新建？** 不一定。连接池可由应用共享管理，但请求身份要显式绑定，不能并发修改共享 client 的默认 Authorization header 来切用户。

**追问二：闭包捕获 user_id 有什么问题？** 如果在共享 Agent 构建时捕获首个用户，会将后续 run 绑定错误身份。动态 instructions / tools 应按本次 RunContext 取可信依赖，而不是从变化的全局变量取。

**追问三：deps 不发送给模型就安全了？** 不自动发送不等于不会泄露；工具返回、日志、动态提示和异常都可能把它序列化出去。按字段最小化，并测试错误路径。

<a id="pai-usage"></a>

### H8：为什么 request_limit=5，账单却不一定只有五次 HTTP 请求？

**第一问：** 2.55.0 的 RunUsage.requests 是什么？本地源码定义为 Agent 循环采纳的模型响应步数，不是 provider 收到的所有尝试。Fallback 放弃的尝试、续接请求、SDK / 传输层重试等与该数字不一一对应。

**追问一：tool_calls_limit 统计所有工具尝试吗？** 当前定义针对成功工具调用；参数纠错和失败尝试还需独立审计。不能用它单独证明“任何工具函数最多执行 N 次”，更不能替代写动作幂等。

**追问二：token / cost 限制能在请求前精确锁账单吗？** 很多计数依赖响应后用量，进行中的输出与额外计费存在窗口；计价还需 provider / 模型映射准确。应同时有单次输出限制、总期限、请求数与业务额度控制。

**追问三：父子显式共用 RunUsage 就是分布式预算了吗？** 不是。单进程对象共享不等于跨 worker 原子额度；并发和远程任务还需应用额度分配与汇总。不要把类型化统计对象当分布式账本。

**追问四：应该记录哪些数字？** 分别记录业务 task、run、循环 step、provider attempt、工具 logical call / attempt / success、token / cost。只有定义计数单位，才有可比的成本和成功率。

### H9：history 里工具调用成对出现，为什么还不能随意截断？

**第一问：** 保留最后十条消息就够吗？可能把 tool call 与对应 result 分开，破坏 provider 协议；也可能丢失当前输出所依赖的授权范围和事实版本。

**追问一：all_messages 和 new_messages 保存策略怎么选？** 要么保存新的完整快照替换旧会话视图，要么在旧历史上只追加本轮新增，不能两者同时追加。跨 run 还有各自 run_id，不能因为同会话就假设是同一次执行。

**追问二：裁剪时把工具结果改成摘要可以吗？** 需维持框架消息结构与配对，且不能把 unknown、denied 总结成 success。摘要用于上下文，原始必要证据另存并可追踪。

**追问三：消息直接 pickle 到处传好吗？** 应采用明确、受支持的序列化方式与版本策略，保护敏感内容，不对不可信输入做危险反序列化。跨版本恢复应有历史样本兼容测试。

### H10：DeferredToolRequests 里面 calls 与 approvals 有什么不同？

**第一问：** 它们都叫 deferred，是一回事吗？不是。审批请求表示先取得许可，再由相应执行路径执行工具；外部 deferred call 则可能要由外部执行者提供结果。业务状态都暂停，并不代表恢复载荷含义相同。

**追问一：只传 ToolApproved 就算工具已成功吗？** 不算。批准代表允许执行，不是成功执行结果；后续权限、前置条件、参数校验、外部执行和验收仍需完成。

**追问二：审批改参怎么防换单？** 绑定 tool_call_id、提案 ID、规范参数摘要、对象版本、审批人、有效期；改参重新校验，超出审批政策则再次确认。tool_call_id 本身不是认证凭据。

**追问三：同一批准重复恢复会怎样？** 不能指望消息历史天然防止所有重复外部执行。应用审批记录需要单次决定与并发控制，工具还应使用业务 action_id 去重。

**追问四：恢复是不是同一个 Python 栈？** 仓库示例是用历史＋DeferredToolResults 启动后续 run；需显式持久化历史与审批数据，重建 deps，并延续业务预算。在线文档可能还有其他处理入口，不要把未使用的入口写成示例已实现。

### H11：工具使用 async def，就没有并发和阻塞问题了吗？

**第一问：** 一个响应里多个工具会怎样？工具可能并行执行，两个调用修改共享 deps、同一文件或同一业务对象，会产生竞争。async 只是执行形式，不保证互斥。

**追问一：sequential=True 能保证什么？** 本地 2.55.0 文档把它描述为本轮工具执行中的屏障：该工具独占执行，不与其他工具调用重叠。它不是跨 run / 跨进程业务锁，也不是业务事务。

**追问二：async 工具里用阻塞 SDK 呢？** 仍可能卡住事件循环；用异步客户端，或在合适线程执行阻塞 I/O，并管理线程与取消边界。CPU 密集任务另考虑进程 / 任务系统。

**追问三：取消能中止正在跑的线程或远程写入吗？** 不能普遍保证。请求可能继续完成；记录已完成和不确定结果，不把取消当回滚。客户端、流和上下文管理器要正确清理。

### H12：不用真模型，怎样测试一次“错参→纠正→审批→重复恢复”？

**第一问：** TestModel 能按预期演出全部吗？它按 schema 生成测试行为，默认可能尝试所有工具，不适合精确模拟语义错误链。FunctionModel 更适合根据历史生成受控调用与输出。

**追问一：测试脚本应该怎么安排？** 第一步返回错误参数，断言未触及真实工具；第二步改正参数并触发审批，断言零写入；拒绝分支不得写，批准分支按绑定参数执行内存替身；重复提交断言替身只有一次业务效果。

**追问二：怎么证明没有真实副作用？** 除禁止真实模型请求外，把依赖替换为内存服务并拦截未预期网络，检查工具实现、fixture 与测试入口。不使用生产 client，不读取真实 env。没有 Key 不是安全证据。

**追问三：这些通过后能说模型会规划吗？** 不能。它只证明程序能正确处理指定轨迹；真实模型评估还要独立授权，在任务集上测工具选择、纠错、拒绝与成本分布。

## 20. 综合设计：类型化 ERP 研究助手，如何避免“合法 JSON、错误业务”？

**题目：** 查询授权范围订单，输出合计与风险解释；未来可能增加审批后的催款草稿发布。要求支持测试、续聊和费用约束。

### 20.1 参考方案：把事实、建议、动作拆开

数据层输出带来源和时点的 Facts，金额由确定性工具计算。Advice 只描述分析结论与证据引用，不混入“已发布”状态；待发布内容形成 Proposal，再交单独审批与执行契约。三者不能用一个宽松 dict 相互冒充。

依赖层按 run 注入可信 tenant、只读订单服务、时钟与预算；模型参数不包含 token 或 tenant 切换。只读查询工具返回有界证据，不返回整个客户对象。

验收层先做结构，再检查订单集合、金额、时点、证据引用；风险自由文本按可验证结论组织，无法严格验真的内容明确标为建议。ModelRetry 只用于模型可修的错误，权限 / 不确定写入结果由应用处理。

历史层保存本轮新增或完整快照中的一种，保留调用配对；续聊中的“按上次范围”要解析并确认，不默认扩大到全量。业务总预算贯穿后续 run、子任务和审批恢复。

### 20.2 四轮质疑参考回答

**“金额字段已经用 Decimal，为何还会错？”** Decimal 解决表示与计算精度，解决不了列含义、币种、采集范围和数据时点；事实层要给这些元信息，业务验收按相同口径计算。

**“模型编一个存在的 evidence_id，不就过了吗？”** 还要校验引用归属本次任务、对应结论确被证据支持。仅检查 ID 存在是必要而非充分条件；高风险结论优先结构化可核对规则。

**“Validator 每次都重新查实时接口，不是更准？”** 多轮查询可能看到不同版本并产生漂移，还增加延迟。按任务契约固定研究快照，执行前再验证必要实时前置条件，区别建议与实际动作。

**“审批后模型又改了正文，怎么办？”** 批准绑定规范化内容摘要，执行端只接受被批准的版本；任何改动产生新提案或重新审批。不能让模型在执行前自由改写已批准载荷。

**“用类型能把这些全部编译期证明吗？”** 不能。类型表达契约，授权、时间、远程结果与并发依赖运行时协议；高级设计应说明哪些错误提前发现，哪些仍需运行时与外部事实验证。

## 21. 阅读源码与面试自测清单

本地阅读入口：Pydantic `config.py` 与模型构造 / 校验入口；PydanticAI 的 `agent/`、`_agent_graph.py`、`tools.py`、`tool_manager.py`、`usage.py`、`models/test.py`。先用公开 API 理解职责，再追踪私有实现；不要在业务代码依赖私有函数名。

| 复杂题 | 合格回答不能缺少 |
| --- | --- |
| strict 与 JSON 字符串 | 按输入模式和类型区分，不说“全不转换” |
| model_copy 后非法 | 区分复制、赋值、默认与实例重验入口 |
| 合法输出却编造 | 结构、内部一致、外部证据、权限分别校验 |
| 五步上限却多次请求 | Agent 循环统计与底层 provider attempts 分开 |
| 并发 deps 串用户 | run 隔离、共享客户端身份绑定、闭包捕获检查 |
| 延迟审批重复执行 | 绑定调用与参数版本、并发防重、业务幂等 |
| TestModel 无 Key 仍写数据 | 模型替身不替代工具依赖隔离 |
| 流式已显示 approve | 中间对象只展示，最终验收后才可执行 |

额外依据：[Pydantic Strict Mode](https://pydantic.dev/docs/validation/latest/concepts/strict_mode/)。本节计数与顺序使用本地 2.55.0 源码核对；不把最新在线文档全部映射为本仓库已演示功能，也不声称本次执行了这些故障测试。

<a id="pydantic-ai-whiteboard"></a>

## 22. 白板演练：类型契约到底在哪一步生效？

### W1：Before、Wrap、After，执行顺序是什么？

不要只背“before 在前、after 在后”，请对下面的 Annotated 写出实际 trace、最终值，以及输入 -3 时会发生什么。示例纯内存，本次仅做语法检查。

```python
from typing import Annotated, Any

from pydantic import AfterValidator, BeforeValidator, TypeAdapter, WrapValidator

trace: list[str] = []


def strip_text(value: Any) -> Any:
    # Before 接收原始输入；不能假设这里已经是 int。
    trace.append("before.strip")
    return value.strip() if isinstance(value, str) else value


def require_positive(value: int) -> int:
    # After 位于内部 int 解析之后，负责此例的业务数值条件。
    trace.append("after.positive")
    if value <= 0:
        raise ValueError("必须为正数")
    return value


def double(value: int) -> int:
    trace.append("after.double")
    return value * 2


def traced_wrap(value: Any, handler: Any) -> Any:
    trace.append("wrap.enter")
    # 调用 handler 才进入内部校验；这里不吞异常、不改成默认成功值。
    result = handler(value)
    trace.append("wrap.exit")
    return result


Amount = Annotated[
    int,
    AfterValidator(require_positive),
    AfterValidator(double),
    BeforeValidator(strip_text),
    WrapValidator(traced_wrap),
]

parsed = TypeAdapter(Amount).validate_python(" 3 ")
assert parsed == 6
assert trace == [
    "wrap.enter", "before.strip", "after.positive", "after.double", "wrap.exit"
]
```

<details>
<summary>参考答案与更深一层的追问</summary>

Annotated 的 before / wrap 从右向左进入，after 再从左向右执行。因此先进入最右 wrap，再 strip，内部解析成整数，执行正数约束、翻倍，最后回到 wrap。默认宽松模式中，本例允许数字字符串被 int 解析。

对 -3，positive 抛错，double 不执行；本例 wrap.exit 不会记录，因为没有 finally。这是题目 trace 的行为，不代表生产审计应该漏记失败退出。

追问一：“Wrap 不调用 handler，直接返回值会怎样？”它可以跳过内部校验，所以 wrapper 代码本身属于可信边界，不能认为所有值必然经过原 int 规则。

追问二：“PlainValidator 呢？”它可替代内部类型校验；如果错误地原样返回任意输入，注解为 int 的字段也可能拿到不符合预期的值。不要把 plain 当普通 after 使用。

追问三：“After 返回的结果一定再次完整验型吗？”不要依赖自动重验。自己编写的 validator 必须维护返回契约；它不是能够任意返回字符串、再由框架无限兜底的函数。

评分：写出顺序与最终值 2 分；解释异常短路 1 分；指出 handler / plain 的跳过风险 1 分；区分示例 trace 与生产审计 1 分。

</details>

### W2：动态隐藏工具后，为什么执行函数里还要检查？

某个工具只允许当前依赖允许读取时向模型展示。请找出下面两处检查分别承担什么职责，以及它们还没解决什么问题。片段只构造 Agent，不调用 run，不创建真实模型客户端；所有业务结果均为虚构。

```python
from dataclasses import dataclass, replace

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.tools import ToolDefinition


@dataclass(frozen=True)
class DemoDeps:
    # 此标志只是示例上下文；生产中应由可信认证 / 授权层提供。
    read_allowed: bool


def prepare_read(
    ctx: RunContext[DemoDeps], definition: ToolDefinition
) -> ToolDefinition | None:
    if not ctx.deps.read_allowed:
        return None  # 当前步不向模型展示此工具，减少误选。
    # 保留原定义的其他字段，不重新构造并意外丢掉 kind / sequential 等设置。
    return replace(definition, description="只读取虚构订单 DEMO-100 的固定金额")


def build_demo_agent(model: Model) -> Agent[DemoDeps, str]:
    agent = Agent(model, deps_type=DemoDeps, output_type=str)

    @agent.tool(prepare=prepare_read)
    def read_amount(ctx: RunContext[DemoDeps], order_number: str) -> dict[str, int]:
        """返回演示金额；不访问数据库、HTTP、文件或真实 ERP。"""
        if not ctx.deps.read_allowed:
            raise PermissionError("本次运行不允许读取")
        if order_number != "DEMO-100":
            raise ValueError("不在演示范围内")
        return {"outstanding_yuan": 125}

    return agent
```

<details>
<summary>参考答案：可发现性不等于授权</summary>

prepare 控制本轮模型可见的工具定义，减少无关 schema 与误调用；执行检查维护工具的边界。工具可能从其他代码入口被调用，展示时到执行时权限也可能变化，因此不应把 schema 隐藏作为唯一授权依据。

这段示例里的两处检查使用同一个静态标志，并没有实现权限实时撤销；真实工具还应向可信授权层确认当前对象归属、用户权限和任务范围。不能把示例改成“每次问模型是否有权限”。

replace 保留未修改字段，但它是浅复制：若接着原地改嵌套 schema 字典，仍需小心共享引用；应只复制必要的嵌套结构，避免不同 run 互相修改定义。

高级追问：“重建一个同名 ToolDefinition，只带名称和 schema 呢？”可能丢掉当前版本定义中的其他字段，尤其表示审批工具的 kind 等，改变实际行为。应检查当前源码与实际定义，保留原有契约，并测试批准前零执行。

评分看能否区分展示、执行、实时权限，以及复制定义不等于深度隔离；不能答成“动态隐藏之后就不需要鉴权”。

</details>

### W3：零结果、服务不可用、模型格式错，怎样避免都变成 None？

给三个输出：①查询成功且匹配为零；②工具服务不可用；③模型输出截断、连 JSON 都不完整。请说明哪些属于业务结果，哪些属于协议 / 运行失败。

<details>
<summary>参考分类与契约设计</summary>

①可以是合法成功：完整结构里有空列表与零合计，并附查询范围。②可由显式 unavailable / partial 分支表达，是否作为最终业务对象取决于契约，但绝不能等价于空列表。③尚未得到合法业务对象，应按截断 / 传输 / 解析错误处理，不能伪造成一份 kind=empty 的业务结果。

用判别联合可以减少“成功但缺 data”“失败却带已执行字段”等不可能组合。例如成功分支要求 orders 与 evidence，受限分支要求 reason 与 missing；字段由 kind 决定，不能只靠 `ok: bool` 加一堆 Optional。

不过联合只能约束结构，分支选择仍需可信依据：模型不能把缺少必需证据的成功改名成 partial，就绕过原来的业务完成标准。应用应明确 partial 是否允许交付、哪些步骤已确认。

扣分点：把异常捕获后统一返回空对象；让 validator 只检查 success 分支；用一段自由文本兜底绕过所有结构化要求。

</details>

## 23. 协议、校验异常与数据保护的补充判断

### 23.1 内部模型、模型输出模型、API 响应模型，可以不同

模型输出需要清晰和有限，内部状态需要证据与执行元数据，对外 API 又需要稳定版本与字段脱敏。可以通过小的显式转换连接，不必把所有模型强行合并为一个万能 BaseModel。

代价是转换代码与 schema 同步，应集中在边界并有断言；收益是避免把内部租户字段、秘密和错误栈直接暴露。不要为每个函数都建一套重复类，也不要为了“少几个类”牺牲信任边界。

### 23.2 规范化、校验、序列化要按顺序区分

规范化决定允许怎样表示同一值，如去除外层空格；校验判断是否合法；序列化决定如何对外表达。过度规范化可能改变业务身份，如把大小写敏感的 ID 强行转小写，或把空金额默认为零。

Schema 的 validation / serialization 视图、alias 与自定义 serializer 也可能不同；模型看到的输入契约应与实际解析方式一致。不要在 serializer 里修正非法业务状态，让错误到输出时才“变得好看”。

### 23.3 输出稳定，不代表工具链可替换

更换模型 / Provider 后即使都能输出 Advice，工具选择、并行行为、拒答、流式与 schema 子集仍可能变化。需要以同一任务集检查行为与费用，不只断言最终能构造 BaseModel。

相关统计口径见本篇 H8；跨框架选型与评估见 [Agent 实战演练](./05_agent_engineering.md#agent-practice)，避免把任何一种类型工具当成全系统保证。

<a id="pai-errors"></a>

### 23.4 相同的异常名称，为什么不能在所有层都当作“让模型重试”？

**版本事实：** Pydantic v2 不再把 validator 内抛出的 `TypeError` 自动转换为 `ValidationError`。例如校验函数把整数当字符串调用方法，可能是程序实现错误，而不是用户输入“不够听话”。修复输入还是修复代码，必须先分清。

| 出现位置与错误 | 正确理解 | 应用处理边界 |
| --- | --- | --- |
| Pydantic validator 主动抛 `ValueError` / `PydanticCustomError` | 声明输入不满足规则，可汇入 ValidationError | 给调用方安全、明确的字段反馈；若来自模型可在预算内纠错 |
| Pydantic validator 抛 `TypeError` | v2 不自动包装，可能是签名、类型使用或函数实现问题 | 保留原始原因，排查程序；不把所有 TypeError 无脑转换成 ModelRetry |
| PydanticAI 工具 / output validator 主动抛 `ModelRetry` | 开发者明确提供可修正的模型反馈 | 确认模型有能力修正、反馈不泄密，并设置尝试与任务总预算 |
| 普通工具函数抛 `ValueError` 或其他异常 | 不等于在 Pydantic validator 中声明字段不合法 | 看所在执行层和本版本处理契约，不假设框架自动转换成模型反馈 |
| 权限拒绝或执行结果未知 | 不是格式小错误 | 停止、重新授权或对账，不让模型换身份 / 重复写入 |

**连续追问一：全部 `except Exception: raise ModelRetry(...)` 可以统一错误吗？** 不可以。它会把程序缺陷、鉴权失败与真实写入的不确定性混进纠错循环；还可能把原始异常里的秘密送回模型。只在明确边界捕获预期异常，并映射为有限错误类别。现代 `asyncio.CancelledError` 属于 BaseException，通常不由 `except Exception` 捕获；也不要因此改用捕获 BaseException 来吞掉取消或框架控制信号。

**连续追问二：业务校验用 `assert amount >= 0` 可以吗？** 教学片段中的 assert 用于表达预期结果；生产输入校验与权限控制不能只靠它。Python `-O` 可移除 assert，导致约束消失。用显式条件和合适异常表达必须一直生效的规则。

**连续追问三：模型改一次还是报相同错误，继续加 retries 吗？** 先判断反馈是否可执行、schema 是否矛盾、工具事实是否缺失，以及错误是否来自代码。增加次数不能修复实现 bug；应有“同类失败重复且无进展”的停止判据。

**验证点：** 对同一字段分别输入非法值、合法边界值和触发 validator 实现错误的值；检查错误类别、保留的原因与反馈内容，并断言权限拒绝不会触发业务重执行。这里只列测试设计，不表示本次执行了这些路径。

<a id="pai-secrets"></a>

### 23.5 SecretStr、exclude 和“没把 deps 发给模型”，为什么还不够？

`SecretStr` 等 Secret 类型可遮掩常见显示 / 序列化场景，但底层仍保存秘密，可经 `get_secret_value()` 取得。自定义 serializer、手动构造 Prompt、SDK 调试与日志都可能重新暴露明文；它不是加密容器或网络隔离。

`Field(exclude=True)` 或某次 `model_dump(exclude=...)` 只控制相关序列化视图，不会清除原对象、其他输出路径或已写出的历史。私有属性也不因名字带下划线就成为秘密保险箱。

错误路径尤其容易遗漏：校验错误可能携带原始 input、字段上下文和自定义错误文本。日志与模型反馈应分别使用允许字段构造安全内容；针对某种显示方式隐藏 input，不等于所有 `.errors()`、异常对象和追踪平台都自动脱敏。

可按“依赖注入→动态提示→工具输入输出→校验失败→日志与 trace→最终响应 / 历史”逐个出口检查。测试使用虚构哨兵秘密，确认它不会出现在非授权出口；不要拿真实 token 做泄露测试，也不要把完整失败载荷直接发给模型让它修复。

面试收束：“类型建模负责契约，Secret 类型降低意外显示风险，应用白名单和观测配置控制外发；三者互补，不互相替代。”跨存储副本的生命周期见 [Agent 运维与数据治理](./05_agent_engineering.md#eng-ops)。

## 24. 面试前的精读顺序与依据

先做 W1，确认知道校验到底发生在哪里；再做 W2，确认能把模型可见性与授权分开；最后做 W3，确认不会把协议失败包装成业务空结果。然后回到第 20 节，完整讲一遍事实、建议、提案、审批和执行的分层。

本轮补充依据：[Pydantic Validators](https://pydantic.dev/docs/validation/latest/concepts/validators/)、[PydanticAI Advanced Tools](https://pydantic.dev/docs/ai/tools-toolsets/tools-advanced/)，并对照本地 functional_validators.py 与 tools.py。文档中的断言是读者可练习的目标，本次没有执行片段，也未证明真实模型会自动选对工具。

# 基于 State 的动态 Skills：机制、路由与安全边界

“动态 Skill”很容易被误解成“运行时动态挂载工具”。在当前 Deep Agents 中，它更准确的含义是：**应用在创建一个 thread 时，把本次允许发现的 Skill 文件放进 State；`SkillsMiddleware` 从配置好的 backend 路径扫描这些文件，并把 Skill 索引提供给模型。**

Skill、工具和权限是三层不同的东西：

- Skill 是任务说明、SOP、示例和配套文件。
- Tool 是模型能够调用的函数或文件操作。
- Permission / HITL / Sandbox 才负责强制授权和隔离。

只给 Agent 一份 Skill，不会自动增加工具，也不会提升工具权限。

## 1. 先纠正“静态全塞、动态按需”的简化图

对当前 `deepagents 0.7.x`，下面这种理解并不准确：

```text
静态 Skills = 把所有 SKILL.md 正文全部塞进 prompt
动态 Skills = 框架读取意图/角色/权限后，只加载几个工具
```

实际机制是：

| 维度 | 固定目录 Skills | `StateBackend` 动态 Skills |
| --- | --- | --- |
| `skills=[...]` 的含义 | 配置要扫描的 backend 目录 | 同样是配置要扫描的 backend 目录 |
| Skill 文件来自哪里 | 文件系统、Store、远程 backend 等 | 本次 thread 的 `state["files"]` |
| 首次进入 thread | 扫描目录并解析 metadata | 扫描 State 文件并解析 metadata |
| 进入模型 prompt | `name`、`description`、路径等索引 | 完全相同 |
| 完整 `SKILL.md` 正文 | 模型需要时调用 `read_file` | 完全相同 |
| 是否自动选择工具 | 否 | 否 |
| 是否自动判断角色和权限 | 否 | 否 |
| 真正的动态点 | backend 内容可由部署方维护 | 应用可为每个新 thread 注入不同文件集合 |

两边都使用 progressive disclosure，不会默认把所有 Skill 正文一次性塞入上下文。Skill 很多时仍会增加 metadata 索引的 token，并增加模型选错 Skill 的概率，因此在进入 Agent 前做可信预筛选仍然有价值。

## 2. 一次真实执行经过哪些步骤

本项目的配置是：

```python
dynamic_skill_agent = create_deep_agent(
    model=MODEL,
    tools=PROCUREMENT_TOOLS,
    backend=StateBackend(),
    skills=["/skills/session/"],
)
```

执行链路如下：

```text
Graph 构建
  │
  ├─ 安装 SkillsMiddleware(sources=["/skills/session/"])
  ├─ 安装 FilesystemMiddleware
  └─ 注册 read_file 等文件工具
  │
  ▼
invoke(input)
  │
  └─ input["files"] 写入 LangGraph State 的 files channel
  │
  ▼
SkillsMiddleware.before_agent
  │
  ├─ StateBackend.ls("/skills/session/")
  ├─ 找到每个一级子目录
  ├─ 读取 <skill-dir>/SKILL.md
  ├─ 解析 YAML frontmatter
  ├─ 按 name 合并多个 source，后者覆盖前者
  └─ 写入私有 state["skills_metadata"]
  │
  ▼
SkillsMiddleware.wrap_model_call
  │
  └─ 把 Skill 名称、描述、路径追加到 system prompt
  │
  ▼
模型判断某 Skill 是否匹配
  │
  ├─ 不匹配：不读取正文，继续普通工具循环
  └─ 匹配：调用 read_file(".../SKILL.md", limit=1000)
                │
                ▼
          完整正文作为工具结果进入当前对话
                │
                ▼
          模型按 Skill 步骤执行任务
```

注意两个时间点：

1. Middleware 首次扫描时必须读取每个 `SKILL.md`，但只解析并保留 frontmatter metadata 供发现使用。
2. 完整正文只有在模型显式调用 `read_file` 后，才作为工具结果进入模型上下文。

所以“backend 读取过文件”和“Skill 正文已经占用模型上下文”不是同一件事。

## 3. State 中究竟有什么

动态 Skill 示例涉及以下状态：

| 字段或配置 | 谁写入 | 用途 | 生命周期 |
| --- | --- | --- | --- |
| `skills=["/skills/session/"]` | Graph 构建代码 | 告诉 Middleware 扫描哪些目录 | Graph 配置，不是 State |
| `state["files"]` | 调用方、文件工具 | 保存 `SKILL.md`、配套文件和任务文件 | 当前 thread；配置 checkpointer 后可恢复 |
| `state["skills_metadata"]` | `SkillsMiddleware.before_agent` | 保存已发现的 Skill 索引 | 当前 thread；私有 Middleware State |
| `state["skills_load_errors"]` | `SkillsMiddleware` | 保存目录或文件加载诊断 | 当前 thread；私有 Middleware State |
| `messages` | 用户、模型、工具 | 对话与 `read_file` 返回的正文 | 当前 thread |
| `Context` 中的身份字段 | 认证后的服务端 | `tenant_id`、角色、策略版本等可信路由输入 | 一次 run，模型不应改写 |

`skills_metadata` 被标记为 `PrivateStateAttr`：它不会作为普通输入/输出字段暴露，也不会传播给父 Agent。它仍属于 Graph 内部 State，并可随 checkpoint 保持“这个 thread 已经扫描过”的事实。

`StateBackend` 的 `files` 不是 Python 全局变量。它通过 LangGraph 的 state channel 读取和写入，因此：

- 没有 checkpointer 时，只在本次执行现场有效。
- 有 checkpointer 且复用同一 `thread_id` 时，后续 run 可以继续读取。
- 换一个 `thread_id` 就是另一份文件和 Skill 集合。
- 它不是跨用户长期仓库；跨 thread 复用应考虑 `StoreBackend` 并做好 namespace 隔离。

## 4. 应用层怎样做可信路由

内置 `SkillsMiddleware` 不读取“意图、角色、权限、任务阶段”并替你做业务路由。正确做法是：认证和策略层先决定允许的 Skill，再把结果放进 State。

```python
from dataclasses import dataclass


@dataclass(frozen=True)
class TrustedIdentity:
    tenant_id: str
    role: str


SKILL_CONTENT = {
    "procurement-review": PROCUREMENT_SKILL,
    "supplier-research": SUPPLIER_RESEARCH_SKILL,
}

ROLE_SKILLS = {
    "buyer": {"procurement-review"},
    "risk-reviewer": {"procurement-review", "supplier-research"},
}


def skill_files_for(identity: TrustedIdentity, task_type: str) -> dict:
    # identity 必须来自认证后的服务端 Context，不能来自模型生成文本。
    allowed = ROLE_SKILLS.get(identity.role, set())
    requested = {
        "purchase": {"procurement-review"},
        "supplier-risk": {"supplier-research"},
    }.get(task_type, set())

    selected = allowed & requested
    return {
        f"/skills/session/{name}/SKILL.md": {
            "content": SKILL_CONTENT[name],
            "encoding": "utf-8",
        }
        for name in selected
    }
```

调用时再组装 State：

```python
identity = TrustedIdentity(tenant_id="tenant-a", role="buyer")

result = dynamic_skill_agent.invoke(
    {
        "messages": [{"role": "user", "content": request_text}],
        "files": skill_files_for(identity, task_type="purchase"),
    },
    config={"configurable": {"thread_id": "purchase-1001"}},
)
```

这里有两层筛选：

```text
服务端确定性筛选：allowed ∩ requested
              │
              ▼
模型语义选择：在允许暴露的 Skill metadata 中判断当前是否需要读取
```

第一层是授权和范围控制，必须确定性执行；第二层只是模型在已授权能力中的任务匹配。

## 5. 为什么同一 thread 不会自动热更新

`SkillsMiddleware.before_agent` 的核心判断是：

```python
if "skills_metadata" in state:
    return None
```

因此 metadata 每个 checkpointed thread 只扫描一次，即使第一次扫描结果是空列表也会缓存。下面三种操作都不会自动刷新索引：

- 给同一 thread 的 `files` 新增一个 Skill。
- 修改已有 `SKILL.md` 的 `name` 或 `description`。
- 删除一个已经进入 metadata 的 Skill。

可能出现的现象：

| 操作 | metadata | 后果 |
| --- | --- | --- |
| 新增 Skill 文件 | 仍是旧索引 | 模型不知道新 Skill 存在 |
| 修改正文、不改 metadata | 索引仍可用 | 下次 `read_file` 可能读到新正文，但行为不易审计 |
| 修改名称或描述 | 仍是旧索引 | 模型继续按旧名称/描述判断 |
| 删除 Skill 文件 | 旧索引仍指向原路径 | 模型调用 `read_file` 时得到不存在错误 |

推荐策略：

1. 一个 thread 的能力集合保持稳定。
2. Skill 集合或策略版本发生变化时创建新 thread。
3. 在 trace metadata 中记录 `skill_profile` 或 `skill_bundle_version`。
4. 确实需要逐轮热切换时，编写专门的动态 Middleware，并明确 metadata 的失效与重建规则；不要只修改 `files` 后假设内置缓存会刷新。

## 6. 多级来源与覆盖顺序

可以配置多个 source：

```python
skills=[
    "/skills/built-in/",
    "/skills/tenant/",
    "/skills/project/",
]
```

加载顺序是从前到后，同名 Skill 由后面的 source 覆盖：

```text
built-in default
       ↓ 同名覆盖
tenant override
       ↓ 同名覆盖
project override
```

这适合“平台默认 → 租户定制 → 项目定制”，但要注意：

- 覆盖依据是 frontmatter 中的 `name`，不是完整路径。
- `name` 应与 `SKILL.md` 的父目录名一致。
- backend 路径统一使用 POSIX `/`，即使运行在 Windows。
- `description` 决定模型是否能正确匹配，应同时说明“做什么”和“什么时候使用”。
- Skill 正文当前有 10 MB 上限；大资料应放引用文件或 RAG，不应塞进一个巨型 `SKILL.md`。

## 7. Skill 不是权限系统

图片中的“权限隔离”只有在应用另外实现强制控制时才成立。仅靠动态 Skill 文件无法做到：

- 隐藏或卸载已有工具。
- 阻止模型调用某个工具。
- 限制 shell、网络、文件或 MCP 能力。
- 验证用户是否真的拥有某个角色。
- 防止跨租户 thread 或 Store namespace 访问。

`SKILL.md` frontmatter 可以写 `allowed-tools`，但当前实现只会把它显示在 Skill 索引中，属于实验性提示信息，并不会自动实施工具 ACL。

真正的控制层应是：

| 目标 | 强制机制 |
| --- | --- |
| 决定本次 Agent 有哪些业务工具 | 构建 Agent 时的 `tools`，或受控的动态工具 Middleware |
| 文件路径授权 | `FilesystemPermission` 与后端访问控制 |
| 高风险动作审批 | `interrupt_on` / HITL |
| 不可信代码执行 | 真正的 Sandbox backend |
| 用户、租户、角色 | 认证后的 Context 与服务端策略 |
| 长期 Skill 隔离 | `StoreBackend` namespace 和服务端授权 |

可以把 Skill 看作“说明书”，不能把说明书当门锁。

## 8. 在 Studio 与 LangSmith 中看什么

运行：

```powershell
uv run langgraph dev --host 127.0.0.1 --port 2024
```

也可以直接使用 CLI；CLI 会把示例 `SKILL.md` 放入本次调用的 `files`：

```powershell
uv run deep-agent-example skill --thread-id skill-001
```

对应的独立 `.py` 文件可以直接运行，并记录 `skill_bundle` trace metadata：

```powershell
uv run python examples/dynamic_skills.py --thread-id skill-py-001
uv run python examples/dynamic_skills.py --role risk-reviewer --task-type supplier-risk
```

脚本中的 `--role` 只是在本地模拟已经认证的服务端 Context；生产 API 不能把客户端传入的 role 直接当成授权事实。脚本实际计算角色允许集合与任务需要集合的交集，没有匹配项时会在调用模型前抛出 `PermissionError`。

不开模型、不上传 trace 的确定性测试：

```powershell
uv run python examples/test_dynamic_skills.py
```

测试使用脚本化 Fake Model，强制产生一次 `read_file` 工具调用，并断言：首次模型请求只有 metadata、读取后完整 `SKILL.md` 才进入消息、同一 thread 新增 Skill 文件不会刷新已经缓存的 metadata。

在 Studio 选择 `dynamic_skill_agent`，输入 README 中带 `files` 的 JSON。观察顺序：

1. 输入 State 中存在 `/skills/session/procurement-review/SKILL.md`。
2. `SkillsMiddleware.before_agent` 在 run 开始时执行。
3. 第一轮模型调用的 system message 中出现 `procurement-review` 的名称、描述和路径。
4. 模型调用 `read_file` 读取该路径，说明完整正文此时才进入对话。
5. 模型继续调用采购工具，并按 Skill 定义的结构输出。

LangSmith 中重点看：

- 模型 span：Skill 索引是否进入 system message。
- `read_file` tool span：模型实际选择了哪个 Skill，是否读取正确路径。
- 后续业务工具 span：模型是否遵守 Skill 的流程，而不是只声称使用了 Skill。
- trace tags / metadata：建议写入 Skill bundle 版本，便于比较不同版本的成功率、token 和延迟。

`SkillsMiddleware` 默认会省略自身 hook span 的大块输入 payload，因此不要只看它的 span 判断正文是否加载；以模型输入和 `read_file` 调用为准。

## 9. 常见故障定位

| 现象 | 优先检查 |
| --- | --- |
| 模型看不到 Skill | `files` 路径是否位于配置的 source 下；目录层级是否是 `<source>/<name>/SKILL.md` |
| Skill 被静默跳过 | frontmatter 是否有 `name`、`description`；UTF-8 是否可解码；查看加载 warning |
| 模型知道 Skill 但没按步骤做 | 是否真的出现 `read_file`；`description` 是否能匹配任务；提示是否要求读取正文 |
| 同一 thread 新增 Skill 后无效 | `skills_metadata` 已缓存；使用新 thread |
| 同名 Skill 内容不是预期版本 | 检查 source 顺序；后面的 source 会覆盖前面的同名 Skill |
| 写了 `allowed-tools` 仍能调用其他工具 | 它不是强制 ACL；在工具/Middleware/HITL 层限制 |
| 不同用户看到相同长期 Skill | 检查 Store namespace、thread 鉴权和服务端路由，不要信任模型给出的租户 ID |

## 10. 什么时候选择哪种方式

| 需求 | 推荐方案 |
| --- | --- |
| 所有 thread 都使用同一套版本化 Skill | `FilesystemBackend` 或只读部署目录 |
| 每个新 thread 根据租户/任务暴露不同 Skill | `StateBackend` + 服务端预路由 |
| 同一用户跨 thread 复用个人 Skill | `StoreBackend` + 用户 namespace |
| 平台、租户、项目分层覆盖 | 多 source，后者覆盖前者 |
| 每一轮都可能切换能力集合 | 自定义 Middleware 和明确的缓存失效策略 |
| 只是检索大量、经常变化的事实 | RAG，而不是把资料做成大量 Skill |
| 要真正限制工具或执行权限 | 工具治理、HITL、Backend 权限和 Sandbox；不要依赖 Skill |

本项目的 `dynamic_skill_agent` 展示的是最容易验证的一种：应用把一个采购 Skill 注入新 thread，Middleware 发现 metadata，模型读取正文，再调用确定性工具完成流程。

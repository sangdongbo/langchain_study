# AI 智能审批助手项目开发方案

## 1. 项目定位

本项目用于开发一个“AI 智能审批助手”。用户进入聊天页面后，系统根据当前登录用户的 `user_id` 获取公司、部门、角色和可用审批权限，再动态加载该公司对应的审批模板。用户可以通过自然语言发起请假、报销、采购、补卡、外出等审批，AI 按模板收集字段、校验信息、生成预览，并在用户确认后提交到现有审批系统。

本开发方案基于前置技术方案 `docs/ai_approval_solution/README.md`，重点说明项目如何拆分、如何开发、如何联调、如何验收。

## 2. 开发目标

第一阶段目标是完成一个可演示、可联调、可扩展的 MVP。

MVP 需要具备：

- 复用现有 Vue2 审批页面，不重新设计或新建前端页面。
- 根据 `user_id` 加载用户上下文。
- 根据公司和权限加载审批模板。
- 支持至少 3 类审批：请假、报销、采购。
- 支持自然语言发起审批。
- 支持字段逐步追问。
- 支持字段修改、取消、重新选择审批类型。
- 支持审批预览。
- 必须用户确认后才提交。
- 支持 mock 审批提交，后续可替换真实审批系统接口。
- 保留 LangGraph 节点流转日志，便于调试和评估。

## 3. 推荐技术栈

### 3.1 前端

现状：

- 前端已有审批页面。
- 当前前端技术栈为 `Vue2`。
- 本阶段暂时不考虑重新设计页面，也不引入 `Vue3`、`React` 或新的前端工程。

前端工作重点：

- 在现有 Vue2 页面中接入 AI 审批助手入口。
- 复用现有审批列表、审批表单、确认提交等页面能力。
- 根据后端返回的结构化结果展示 AI 回复、审批预览和可操作项。
- 必要时新增少量 Vue2 组件或弹窗，但不重做整体页面。
- 保持现有页面风格和交互习惯。

### 3.2 后端

推荐：

- `FastAPI`
- `LangGraph`
- `LangChain`
- `DeepSeek Chat`
- `Pydantic`
- `Redis`，可选，用于保存会话状态。

### 3.3 向量数据库

MVP 阶段：

- 可以先不接向量数据库，只做审批发起闭环。
- 如果要演示制度问答，可使用 `Chroma`。

正式阶段：

- `pgvector`
- `Milvus`
- `Qdrant`

选择原则：

- 公司已有 PostgreSQL：优先 `pgvector`。
- 知识库规模较大：考虑 `Milvus` 或 `Qdrant`。
- 本地快速验证：使用 `Chroma`。

### 3.4 观察与评估

建议：

- `LangSmith`：追踪 LangGraph 节点、模型输入输出、Tool Call。
- 后端日志：记录会话 ID、用户 ID、节点流转、接口调用、错误信息。
- 前端埋点：记录用户确认、取消、修改、提交成功等动作。

## 4. 项目目录建议

可以新建一个独立业务目录，例如：

```text
ai_approval_assistant/
├── backend/
│   ├── app/
│   │   ├── main.py
│   │   ├── api/
│   │   │   ├── chat.py
│   │   │   ├── approvals.py
│   │   │   └── health.py
│   │   ├── graph/
│   │   │   ├── state.py
│   │   │   ├── nodes.py
│   │   │   ├── router.py
│   │   │   └── builder.py
│   │   ├── services/
│   │   │   ├── user_context_service.py
│   │   │   ├── approval_template_service.py
│   │   │   ├── approval_submit_service.py
│   │   │   ├── model_service.py
│   │   │   └── rag_service.py
│   │   ├── schemas/
│   │   │   ├── chat.py
│   │   │   ├── approval.py
│   │   │   └── user.py
│   │   ├── mock_data/
│   │   │   ├── users.json
│   │   │   ├── approval_templates.json
│   │   │   └── policies/
│   │   └── config.py
│   └── tests/
│       ├── test_graph_flow.py
│       ├── test_field_collection.py
│       └── test_submit_guard.py
├── frontend-vue2-existing/
│   ├── approval-page/
│   │   └── 复用现有审批页面
│   ├── api/
│   │   └── 新增 AI 审批助手接口封装
│   └── components/
│       └── 必要时新增少量 Vue2 对话或预览组件
├── docs/
│   ├── api_contract.md
│   ├── graph_flow.md
│   └── test_cases.md
└── README.md
```

如果当前仓库只是学习和方案整理，也可以先不创建完整代码目录，等方案确认后再开发。

## 5. 后端开发方案

### 5.1 FastAPI 接口

建议提供以下接口：

```http
POST /api/ai-approval/chat
```

用途：

- 前端每发送一句用户消息，就调用该接口。
- 后端运行 LangGraph。
- 返回 AI 回复、当前状态、审批预览、可操作按钮。

请求示例：

```json
{
  "session_id": "S001",
  "user_id": "U001",
  "message": "我要报销餐饮费 2000 元，客户招待，发票已提供"
}
```

返回示例：

```json
{
  "session_id": "S001",
  "status": "awaiting_confirmation",
  "assistant_message": "请确认是否提交报销申请。",
  "approval_type": "expense",
  "preview": {
    "title": "报销申请",
    "fields": [
      {"label": "报销类型", "value": "餐饮费"},
      {"label": "金额", "value": "2000"},
      {"label": "事由", "value": "客户招待"},
      {"label": "发票", "value": "已提供"}
    ],
    "approval_node": "直属主管审批"
  },
  "actions": ["confirm", "modify", "cancel"]
}
```

### 5.2 LangGraph 状态

建议状态结构：

```python
class ApprovalState(TypedDict, total=False):
    session_id: str
    user_id: str
    company_id: str
    dept_id: str
    role: str
    user_message: str
    intent: str
    current_template: dict | None
    available_templates: list[dict]
    approval_type: str | None
    collected_slots: dict[str, str]
    awaiting_field: str | None
    confirmation_status: str
    trace_history: list[dict]
    errors: list[str]
    preview: dict | None
    request_id: str | None
    status: str
```

核心字段：

- `current_template`：当前审批模板。
- `collected_slots`：已经收集到的字段。
- `trace_history`：节点流转记录。
- `awaiting_field`：当前等待用户补充的字段。
- `confirmation_status`：是否已经确认提交。

### 5.3 LangGraph 节点

建议节点：

- `load_user_context`
- `load_available_templates`
- `classify_intent`
- `match_approval_template`
- `collect_slots`
- `validate_slots`
- `build_preview`
- `handle_modify`
- `handle_cancel`
- `confirm_submit`
- `submit_application`
- `rag_answer`
- `fallback_clarify`

关键设计：

- 用户未确认时，绝不进入 `submit_application`。
- 用户修改字段后，必须重新进入 `validate_slots` 和 `build_preview`。
- 用户切换审批类型时，清空当前审批字段，重新加载模板。
- 用户说取消时，清空当前审批状态。
- 模型判断低置信度时，进入 `fallback_clarify`。

### 5.4 Mock 服务

MVP 阶段建议先写 mock 服务：

- `mock_get_user_context(user_id)`
- `mock_get_approval_templates(company_id, user_id)`
- `mock_get_approval_template_detail(company_id, approval_type)`
- `mock_validate_approval(approval_type, slots)`
- `mock_submit_approval(user_id, approval_type, slots)`

这样可以在审批系统真实接口未准备好之前，先完成 AI 流程和现有 Vue2 页面的基础联调。

### 5.5 Tool Call 设计

建议把企业系统能力封装成 Tool：

- `get_user_context`
- `list_approval_templates`
- `get_approval_template_detail`
- `validate_approval_form`
- `submit_approval_request`
- `query_leave_balance`
- `query_approval_status`

注意：

- 模型不能直接决定提交。
- Tool 返回结果必须由后端检查。
- Tool 调用失败时要有明确错误状态。

## 6. 前端接入方案

### 6.1 基本原则

当前已有 Vue2 审批页面，因此本阶段不把前端作为主要建设内容。开发重点放在后端 AI 编排、审批模板接口、字段收集和提交链路。前端只做必要接入，保证用户能在现有页面中使用 AI 审批能力。

接入原则：

- 不重做页面。
- 不升级前端技术栈。
- 不引入新的大型 UI 框架。
- 尽量复用现有审批入口、表单、弹窗、按钮和提交逻辑。
- AI 返回结构化数据，前端负责展示和触发用户操作。

### 6.2 需要前端配合的点

现有 Vue2 页面需要配合：

- 增加 AI 助手入口，例如按钮、侧边栏或弹窗入口。
- 调用 `POST /api/ai-approval/chat`。
- 展示 AI 回复内容。
- 展示后端返回的审批预览字段。
- 提供确认、修改、取消操作。
- 将当前登录用户信息或登录态传给后端，后端再解析真实 `user_id`。
- 处理接口 loading、错误提示和防重复提交。

### 6.3 审批预览展示

审批预览可以优先复用现有审批表单或详情组件，不一定单独新做卡片。

推荐展示内容：

- 审批类型。
- 已收集字段。
- 缺失字段提示。
- 预计审批节点。
- 确认提交按钮。
- 修改入口。
- 取消入口。

### 6.4 字段修改方式

字段修改可以有两种方式：

- 用户继续通过聊天修改，例如“金额改成 3000”。
- 用户在现有 Vue2 表单中直接修改字段，再提交给后端重新校验。

第一阶段建议先支持聊天修改，减少前端改造量；如果现有表单改造成本不高，再支持表单内直接编辑。

### 6.5 提交结果展示

提交成功后复用现有审批结果展示方式。

建议展示：

- 申请编号。
- 当前状态。
- 当前审批节点。
- 查看详情入口。

### 6.6 本阶段不处理的前端事项

- 不重新设计审批页面。
- 不升级到 Vue3。
- 不新建独立 React 页面。
- 不做移动端专项适配。
- 不做飞书/企微卡片。

## 7. RAG 开发方案

RAG 不是第一阶段必做，但建议预留接口。

### 7.1 使用场景

- 用户问“报销需要发票吗？”
- 用户问“请年假有什么要求？”
- 用户问“外出申请和出差申请有什么区别？”
- 用户问“采购超过多少钱需要主管审批？”

### 7.2 数据处理

制度文档处理流程：

1. 收集制度文档。
2. 按公司、审批类型、制度版本标注元数据。
3. 切分文档。
4. 调用 Embedding 模型生成向量。
5. 写入向量数据库。
6. 查询时按公司和审批类型过滤，再做向量检索。

### 7.3 第一阶段建议

第一阶段可以只保留 `rag_answer` 节点和接口结构，不强制接入真实知识库。等审批流程稳定后，再补制度问答能力。

## 8. 开发阶段划分

### 阶段 1：需求和接口确认

产出：

- 审批类型清单。
- 字段配置清单。
- 用户上下文接口说明。
- 审批模板接口说明。
- 提交接口说明。
- 现有 Vue2 页面可接入点说明。

### 阶段 2：后端流程 MVP

产出：

- FastAPI 服务。
- LangGraph 状态和节点。
- mock 用户和审批模板数据。
- mock 提交接口。
- 单元测试。

### 阶段 3：现有 Vue2 页面接入

产出：

- 在现有 Vue2 页面中接入 AI 助手入口。
- 接入后端 chat 接口。
- 能展示 AI 回复和审批预览。
- 能触发确认、修改、取消操作。
- 与现有审批页面能力保持一致。

### 阶段 4：真实接口联调

产出：

- 用户上下文接口接入。
- 审批模板接口接入。
- 审批预校验接口接入。
- 审批创建接口接入。
- 错误处理和日志。

### 阶段 5：评估和优化

产出：

- 测试用例集。
- 对话成功率统计。
- 节点流转日志分析。
- 用户反馈。
- 第二阶段扩展建议。

## 9. 测试方案

### 9.1 后端单元测试

重点测试：

- 用户上下文加载。
- 审批模板匹配。
- 字段收集。
- 字段修改。
- 取消流程。
- 未确认不能提交。
- 确认后才能提交。
- 错误字段能重新追问。

### 9.2 对话流程测试

示例用例：

```text
用户：我要请年假
AI：请告诉我请假开始时间
用户：下周一到周三
AI：请补充请假原因
用户：家里有事
AI：生成请假预览
用户：确认提交
AI：返回申请编号
```

修改用例：

```text
用户：我要报销餐饮费 2000 元，客户招待，发票已提供
AI：生成报销预览
用户：金额改成 1800
AI：重新生成预览
用户：确认提交
AI：返回申请编号
```

取消用例：

```text
用户：我要采购电脑
AI：请告诉我采购数量
用户：不买了
AI：已取消本次审批申请，没有提交任何内容
```

### 9.3 前端测试

重点检查：

- 聊天消息顺序正确。
- 审批预览字段正确。
- 修改按钮可用。
- 确认按钮只在预览阶段出现。
- 提交中按钮禁用。
- 提交失败能展示错误。
- 现有 Vue2 页面接入后不影响原审批功能。

### 9.4 联调测试

重点检查：

- `user_id` 是否正确传入。
- 不同公司加载不同审批模板。
- 无权限审批不能发起。
- 审批预校验失败时不允许提交。
- 接口超时时不误提交。
- 提交成功后申请编号正确展示。

## 10. 验收标准

第一阶段验收标准：

- 能根据 `user_id` 获取用户公司和可用审批模板。
- 能完成请假、报销、采购三类审批的完整对话流程。
- 能处理字段缺失、修改、取消。
- 提交前有清晰预览。
- 未确认不提交。
- 确认后能调用 mock 或测试接口提交。
- 现有 Vue2 页面完成 AI 助手入口和基础交互接入。
- 后端有基础单元测试。
- 关键节点有日志。

## 11. 风险和应对

| 风险 | 表现 | 应对 |
|---|---|---|
| 模型误判审批类型 | 用户想报销，AI 进入采购流程 | 规则优先，模型兜底；低置信度时澄清 |
| 字段抽取错误 | 金额、日期、数量抽错 | 提交前预览；字段类型校验；允许修改 |
| 未确认误提交 | AI 直接调用提交接口 | LangGraph 强制确认节点；后端提交守卫 |
| 多公司模板差异大 | 一个流程无法适配所有公司 | 所有字段和规则从模板接口读取 |
| 审批接口不稳定 | 提交失败或超时 | 明确错误提示；不自动重复提交 |
| 前端改造范围失控 | 从 AI 能力接入变成重做页面 | 明确复用现有 Vue2 页面，只做必要入口和接口接入 |

## 12. 人员分工建议

| 角色 | 工作内容 |
|---|---|
| 产品/业务 | 确认试点审批类型、字段规则、验收标准 |
| 后端 | FastAPI、LangGraph、接口编排、日志、测试 |
| 前端 | 在现有 Vue2 页面中接入 AI 助手入口、接口调用、预览展示和确认操作 |
| 审批系统负责人 | 提供模板、预校验、提交、状态查询接口 |
| AI 工程 | Prompt、字段抽取、RAG、LangSmith 评估 |
| 测试 | 对话流程测试、接口联调测试、异常场景测试 |

## 13. 建议排期

如果接口和审批字段能及时确认，可以按 4 周左右推进：

| 周期 | 重点 | 产出 |
|---|---|---|
| 第 1 周 | 需求确认、接口确认、现有页面接入点确认 | 字段清单、接口文档、Vue2 接入点说明 |
| 第 2 周 | 后端 LangGraph MVP | mock 流程、单元测试、chat 接口 |
| 第 3 周 | 现有 Vue2 页面接入 | AI 入口、接口调用、预览展示、确认/修改/取消 |
| 第 4 周 | 联调、测试、优化 | 演示版本、测试报告、问题清单 |

如果审批系统接口暂时无法提供，可以先用 mock 接口完成前后端闭环，再替换真实接口。

## 14. 第一版建议优先级

P0：

- 请假申请。
- 报销申请。
- 用户确认后提交。
- 字段修改。
- 取消流程。
- 审批预览。

P1：

- 采购申请。
- 审批状态查询。
- 假期余额查询。
- 制度问答 RAG。

P2：

- 更多审批类型。
- 多公司模板管理后台。
- 附件上传。
- 飞书/企微卡片。
- 统计看板。

## 15. 结论

项目开发建议先做“现有 Vue2 页面接入 + mock 审批接口 + LangGraph 流程闭环”。不要一开始就追求接入全部审批类型，也不要把重点放在模型炫技或页面重构上。第一阶段最重要的是验证：用户能否通过自然语言顺畅发起审批，系统能否稳定收集字段、允许修改、生成预览，并在用户确认后提交。

只要这个闭环跑通，后续扩展更多审批类型、本地制度知识库、飞书/企微卡片、真实审批接口都会更自然。

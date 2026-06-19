# 日报日志 Agent 设计

## 背景

现有 `ai_approval_assistant` 已经有顶层多 Agent 编排：会话记忆、用户信息、审批发起和通用聊天在同一个 LangGraph 状态中协作。现在需要新增一个写日志/日报的 Agent，能力对应页面上的“写日志”弹窗：初始化表单字段、日报配置、当天草稿和同步数据，收集用户确认后的工作内容与自定义字段，最后在用户确认后直接提交日报。

该能力属于独立业务 Agent，不应放进审批发起 Agent 内部。

## 目标

- 新增 `daily_report_agent`，与 `user_info_agent`、`approval_creation_agent`、`general_chat` 并列。
- 用户表达“写日报、写日志、提交今天日报、今日志”等意图时，由顶层 `intent_router` 路由到日报 Agent。
- 进入日报流程后必须请求页面初始化所需的四个接口。
- 支持日报正文 `content` 的用户确认约束：未由用户明确输入或确认的内容不得提交。
- 支持自定义字段：从 `formFields` 读取字段定义，提交时原样携带 `extend_fields`，并按 `field_key` 组装 `extends`。
- 在用户回复“确认提交”后调用 `/oa/dailyReport/add` 创建日报。
- 复用现有会话状态、请求头凭证、接口日志、确认后提交和错误收敛模式。

## 非目标

- 第一版不实现附件上传，`files` 默认提交空数组。
- 第一版不实现复杂的前端选择器联动，只返回可渲染的等待输入描述。
- 第一版不创建、迁移、刷新或读取数据库。
- 第一版不运行 Laravel/PHP 数据库相关测试，不执行任何数据库命令。
- 第一版不做前端打包或构建。

## 顶层编排

日报 Agent 挂在顶层图中，与用户信息和审批发起 Agent 同级：

```text
memory_agent
  -> intent_router
      -> user_info_agent
      -> approval_creation_agent
      -> daily_report_agent
      -> general_chat
```

`intent_router` 增加日报意图识别。第一版采用以下优先级：

1. 用户信息问题优先进入 `user_info_agent`。
2. 已有未完成日报上下文时，继续进入 `daily_report_agent`。
3. 已有未完成审批上下文时，继续进入 `approval_creation_agent`。
4. 明确日报关键词进入 `daily_report_agent`。
5. 明确审批关键词进入 `approval_creation_agent`。
6. 普通问候或问答进入 `general_chat`。

日报和审批都可能有“确认提交”阶段，所以必须通过当前状态判断确认对象。`daily_report_agent` 只能提交日报状态中的预览，不能误触发审批提交。

## 日报 Agent 内部流程

```text
daily_report_agent
  -> load_daily_report_context
  -> collect_content
  -> collect_custom_fields
  -> preview_daily_report
  -> submit_daily_report
```

### `load_daily_report_context`

进入日报流程后加载页面等价上下文。以下四个接口为必调接口：

1. `POST /api/field/formFields`

```json
{
  "field_form": "daily_reports"
}
```

2. `GET /oa/dailyReport/config/get?need_parse=1`

3. `GET /oa/dailyReport/draft/get?type=1&date=YYYY-MM-DD`

`type=1` 表示日报，`date` 默认为当前日期，也允许用户在消息中指定日期。

4. `POST /api/oa/dailyReport/syncData`

```json
{
  "daily_report_type": 1,
  "sync_type": [
    "process",
    "followup",
    "order",
    "work_ticket",
    "customer_manage"
  ],
  "date_range": [
    "YYYY-MM-DD",
    "YYYY-MM-DD"
  ]
}
```

这些接口只用于初始化和辅助生成，不代表提交。任一接口失败时不允许提交，Agent 返回可理解错误，并保留可恢复状态。

### `collect_content`

`content` 是核心正文，必须满足用户确认约束。

- 如果草稿接口返回已有正文，Agent 展示草稿并询问用户是否使用或修改。
- 如果用户本轮消息已经明确提供正文，Agent 将其作为候选正文进入预览。
- 如果用户要求“根据同步数据帮我整理”，Agent 可以基于 `syncData` 生成候选正文，但状态必须进入 `awaiting_content_confirmation`。
- 未经用户确认的候选正文不得写入最终提交 payload。
- 用户可以在预览前或预览后修改正文，修改后重新生成预览。

### `collect_custom_fields`

自定义字段来自 `formFields` 返回的字段定义。Agent 保存两份结构：

- `daily_report_extend_fields`：提交时原样放入 `extend_fields`。
- `daily_report_fields`：内部追问、校验和构建 `extends` 使用。

第一版支持字段类型：

| 远程字段类型 | 等待输入类型 | 提交值 |
| --- | --- | --- |
| `input` | `text` | `{"value": "用户输入"}` |
| `textarea` | `textarea` | `{"value": "用户输入"}` |
| `radio` / `select` | `single_select` | `{"value": 选项值, "text": "选项文本"}` |
| `checkbox_approval` | `approval_link_select` | `{"value": []}`，第一版默认空数组 |
| `checkbox_check_record` | `check_record_select` | `{"value": []}`，第一版默认空数组 |

必填字段根据 `is_required == 1` 追问。非必填字段第一版可以跳过，按空值或空数组提交；如果用户主动提供，则写入 `extends`。

示例：

```json
{
  "extends": {
    "field_513687": {
      "value": "1122"
    },
    "field_513692": {
      "value": 1,
      "text": "单选1"
    },
    "field_514141": {
      "value": "22"
    },
    "field_514663": {
      "value": []
    },
    "field_514664": {
      "value": []
    }
  }
}
```

### `preview_daily_report`

预览阶段展示用户即将提交的结构：

- 日志类型：日报
- 日志时间
- 工作内容
- 自定义字段及其值
- 汇报给谁
- 抄送给谁
- 附件数量
- 同步数据摘要

预览后状态进入 `awaiting_daily_report_confirmation`。用户可以回复：

- “确认提交”：进入提交节点。
- “取消”：取消当前日报流程，不调用提交接口。
- “修改内容为...”或“单选改成...”：更新字段后重新预览。
- 普通问题：可以进入通用回答，但应附带继续当前日报流程的提示。

### `submit_daily_report`

只有在状态为 `awaiting_daily_report_confirmation` 且本轮消息为确认提交时，才允许调用提交接口：

`POST /oa/dailyReport/add`

提交 payload：

```json
{
  "type": 1,
  "date": "YYYY-MM-DD",
  "content": "用户确认后的工作内容",
  "files": [],
  "at_uids": [],
  "recipients": [],
  "cc_recipients": [],
  "extends": {},
  "extend_fields": []
}
```

字段来源：

- `type`：第一版固定为 `1`。
- `date`：用户指定日期或当前日期。
- `content`：用户明确输入或确认后的正文。
- `files`：第一版为空数组。
- `at_uids`：第一版为空数组，不从正文自动解析 `@`。
- `recipients`：优先使用草稿返回值，其次使用日报配置默认汇报人，用户可修改。
- `cc_recipients`：优先使用草稿返回值，其次使用日报配置默认抄送人，用户可修改。
- `extends`：由自定义字段收集结果组装。
- `extend_fields`：来自 `formFields` 的字段定义，原样携带。

提交成功后状态进入 `daily_report_submitted`，返回提交成功消息和接口返回的日报 ID 或状态。提交失败时保留预览和已收集内容，允许用户重试。

## 服务分层

新增日报服务边界，避免日报逻辑混进审批服务。

```text
app/services/daily_report_api_client.py
app/services/daily_report_service.py
app/services/daily_report_mapper.py
app/agents/daily_report_agent.py
app/agents/daily_report/
  inputs.py
  payload_builder.py
  responses.py
  routing.py
  state_helpers.py
```

### `DailyReportApiClient`

只负责 HTTP 请求、请求头、日志和响应 JSON：

- `get_form_fields(user)`
- `get_config(user)`
- `get_draft(user, report_type, date)`
- `sync_data(user, report_type, date, sync_types)`
- `add_daily_report(user, payload)`

请求头复用现有 CRM 接口风格：

```text
Accept: application/json, text/plain, */*
Content-Type: application/json;charset=UTF-8
Authorization: <user.authorization>
UID: <user.uid>
```

### `DailyReportService`

负责业务语义：

- 加载日报上下文。
- 解析日报类型、日期、草稿、默认汇报人和抄送人。
- 解析自定义字段。
- 校验必填正文和必填自定义字段。
- 构建预览和提交 payload。
- 调用提交接口。

### `daily_report_mapper`

负责字段映射：

- 远程字段定义到内部字段模型。
- 选项字段的 `value/text` 匹配。
- `extends` 默认值生成。
- 草稿中的 `extends` 回填。

## 状态字段

在现有 `ApprovalState` 共享状态中新增日报字段。第一版保持兼容，不大规模重命名。

```text
daily_report_status
daily_report_type
daily_report_date
daily_report_content
daily_report_content_confirmed
daily_report_fields
daily_report_extend_fields
daily_report_extends
daily_report_config
daily_report_draft
daily_report_sync_data
daily_report_recipients
daily_report_cc_recipients
daily_report_preview
daily_report_request_id
_daily_report_route
```

第一版使用以下日报状态：

- `idle`
- `loading`
- `collecting_content`
- `awaiting_content_confirmation`
- `collecting_custom_fields`
- `awaiting_daily_report_confirmation`
- `daily_report_submitted`
- `cancelled`
- `error`

## API 响应

现有 `ChatResponse` 面向审批命名较多。第一版为了少改前端入口，复用以下字段并新增日报预览字段：

- `status`：扩展现有枚举，加入日报流程状态。
- `assistant_message`：返回日报追问、预览和提交结果。
- `awaiting_input`：返回正文、自定义字段、汇报人和抄送人的结构化输入。
- `daily_report_preview`：新增日报专用预览，避免日报套审批语义。
- `trace`：加入 `daily_report_agent` 和内部节点名称。

第一版新增日报专用响应结构，同时保持 `/api/ai-approval/chat` 入口兼容。

## 错误处理

- 缺少 `authorization` 或 `uid`：提示登录态不可用，不调用远程接口。
- 初始化接口失败：返回失败接口和简短原因，不进入提交。
- `content` 为空：追问用户输入工作内容。
- `content` 未确认：不允许提交。
- 必填自定义字段为空：逐项追问。
- 单选值无法匹配：返回候选项让用户选择。
- 提交接口失败：保留当前预览，允许用户回复“重试提交”。
- 已提交状态再次确认：返回已提交结果，不重复调用提交接口。

## 测试与验证

遵守全局数据库安全规则。测试前需要确认测试不会触碰数据库；不得运行 Laravel `artisan test`、`phpunit`、`pest` 或任何迁移、刷新、seed 命令。

第一版添加纯 Python 单元测试：

- `DailyReportApiClient` 请求方法构造正确 URL、method、headers 和 body。
- `daily_report_mapper` 正确映射 `input`、`textarea`、`radio`、关联审批单和打卡记录字段。
- `payload_builder` 正确生成 `/oa/dailyReport/add` payload。
- `daily_report_agent` 在未确认 `content` 时不会提交。
- `daily_report_agent` 在预览确认后才调用 `add_daily_report`。
- 顶层 `intent_router` 将日报意图路由到 `daily_report_agent`。

实现后优先运行不触碰数据库的静态和单元验证，例如：

```powershell
python -m compileall ai_approval_assistant/app
```

若运行 pytest，必须先检查相关测试、基类、fixture 和配置，确认不会访问数据库。

## 实施顺序

1. 增加 endpoint 配置项：日报字段、配置、草稿、同步数据、提交接口。
2. 增加日报 schema、mapper、payload builder。
3. 增加 `DailyReportApiClient` 和 `DailyReportService`。
4. 扩展共享状态和响应结构。
5. 增加 `daily_report_agent` 内部状态机。
6. 扩展顶层 workflow 和 `intent_router`。
7. 增加纯单元测试和 compile 验证。
8. 更新 README 中的多 Agent 编排说明。

## 设计决策

- `daily_report_agent` 与审批 Agent 并列，避免日报流程污染审批模板、审批节点和审批提交语义。
- 四个初始化接口在 `load_daily_report_context` 阶段统一请求，保持和页面操作一致。
- `/api/oa/dailyReport/syncData` 只作为同步数据来源，不作为提交接口。
- `/oa/dailyReport/add` 是唯一提交接口，必须由确认节点调用。
- `content` 可以由 Agent 整理候选文案，但必须经用户明确确认后才能提交。
- 自定义字段是核心能力，不延后；`extend_fields` 原样带回，`extends` 按字段 key 和类型构建。

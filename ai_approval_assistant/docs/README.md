# Graph 调试

导出 LangGraph 流程图：

```bash
.venv/bin/python scripts/export_graph.py
```

生成文件：

```text
docs/approval_graph.mmd
```

业务会话级流程图：

```text
docs/session_flow.mmd
```

LangGraph Studio 调试说明：

```text
docs/studio_debug.md
```

可以把 `.mmd` 内容粘贴到 Mermaid Live Editor，或者在支持 Mermaid 的 Markdown 工具里查看。

接口返回里的 `trace` 可以和图对照看，例如：

```json
["memory_agent", "user_profile_agent", "intent_router", "approval_creation_agent", "load_context", "classify", "decision_review", "collect", "validate", "assignee", "preview"]
```

这表示本轮先经过顶层多 Agent 编排，然后进入审批发起子图，识别审批类型，经过有界复核，收集字段，预校验，检查审批流程节点，最后生成预览。

常见 trace：

| trace 片段 | 含义 |
|---|---|
| `["memory_agent", "user_profile_agent", "intent_router", "general_chat"]` | 普通聊天或帮助问句，不进入审批模板搜索 |
| `["memory_agent", "user_profile_agent", "intent_router", "user_info_agent"]` | 查询当前用户、上级、部门等信息，不进入审批流程 |
| `["memory_agent", "intent_router", "daily_report_agent", "load_daily_report_context", "save_daily_report_draft", "preview_daily_report"]` | 写日志/日报子图，加载字段、草稿和同步数据，保存草稿并生成提交前预览 |
| `["memory_agent", "intent_router", "daily_report_agent", "submit_daily_report"]` | 用户确认后提交日报 |
| `["memory_agent", "user_profile_agent", "intent_router", "approval_creation_agent", "load_context", "classify", "decision_review", "clarify"]` | 审批发起需要用户澄清，比如多个模板待选择 |
| `["memory_agent", "user_profile_agent", "intent_router", "approval_creation_agent", "load_context", "classify", "decision_review", "collect"]` | 已进入审批字段收集 |
| `["memory_agent", "user_profile_agent", "intent_router", "approval_creation_agent", "load_context", "classify", "decision_review", "collect", "validate", "assignee"]` | 字段完整后获取审批节点，需要选择办理人/审批人 |
| `["memory_agent", "user_profile_agent", "intent_router", "approval_creation_agent", "load_context", "classify", "decision_review", "collect", "validate", "assignee", "preview"]` | 已生成提交前预览 |
| `["memory_agent", "user_profile_agent", "intent_router", "approval_creation_agent", "load_context", "classify", "decision_review", "submit"]` | 用户明确确认后提交审批 |

流程里有 `decision_review` 节点时，表示进入了有界决策复核。它用于接入模型复核，但必须有最大次数限制，避免无限重复思考。

前端联调时重点看响应里的：

- `awaiting_input`：当前应该渲染的控件。
- `answer`：下一轮请求里回传的结构化值。
- `awaiting_field_key` / `awaiting_field_label`：当前字段 key 和展示名。
- `trace`：本轮 graph 走过的节点。

时光回溯调试时重点看：

- Swagger：服务启动后打开 `http://127.0.0.1:8010/docs`，查看 `time-travel` 分组。
- `GET /api/ai-approval/time-travel/{session_id}/checkpoints?user_id=...`：查看每轮聊天后的 checkpoint 列表。
- `GET /api/ai-approval/time-travel/{session_id}/checkpoints/{checkpoint_id}?user_id=...`：查看某个 checkpoint 的状态快照。
- `POST /api/ai-approval/time-travel/{session_id}/restore`：把当前会话恢复到历史状态。
- `POST /api/ai-approval/time-travel/{session_id}/fork`：从历史状态复制出一个新的 `session_id`。
- Redis key：`{REDIS_PREFIX}ai_approval:checkpoints:{session_id}`；无 Redis 时回退内存。
- 当前学习版时光回溯由 chat turn 外层记录；同时生产 graph 已挂 LangGraph checkpointer，用于 `interrupt`/resume 的线程恢复。

日报联调时还要重点看：

- `daily_report_payload`：agent 根据字段、草稿、同步数据和用户补充内容生成的完整提交 payload。
- `daily_report_preview`：确认提交前展示给用户看的预览。
- `ui_action.type == "interrupt"`：日报内容、日期和确认弹窗都走这套人机协作协议。

运行时存储和性能：

- 会话状态支持 Redis：`{REDIS_PREFIX}ai_approval:session:{session_id}`，TTL 由 `AI_APPROVAL_SESSION_TTL_SECONDS` 控制。
- 短期会话记忆保存在同一个 session 状态里，随 Redis TTL 自动过期；默认保留最近 10 轮，可用 `AI_APPROVAL_SHORT_MEMORY_TURNS` 调整。
- 远程模板、表单字段、动态下拉都有 TTL 缓存，分别由 `AI_APPROVAL_TEMPLATE_CACHE_TTL_SECONDS` 和 `AI_APPROVAL_DYNAMIC_OPTIONS_CACHE_TTL_SECONDS` 控制。
- CRM/ERP 调用会写 `crm.<接口>.timing` 日志，包含 `duration_ms`、`success`、`status_code` 和错误摘要。
- `_child` 控件组会展开必填子字段，并保留 `group_key`、`group_label`、`group_type`，用于后续复杂明细组装。
- 日报自定义字段由 `extends` 和 `extend_fields` 承载，agent 会沿用草稿值和字段接口结构。

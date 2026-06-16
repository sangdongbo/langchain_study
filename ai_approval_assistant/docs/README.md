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
["load_context", "classify", "decision_review", "collect", "validate", "assignee", "preview"]
```

这表示本轮从加载上下文开始，识别审批类型，经过有界复核，收集字段，预校验，检查审批流程节点，最后生成预览。

常见 trace：

| trace 片段 | 含义 |
|---|---|
| `["load_context", "classify", "decision_review", "general_chat"]` | 普通聊天或帮助问句，不进入审批模板搜索 |
| `["load_context", "classify", "decision_review", "clarify"]` | 需要用户澄清，比如多个模板待选择 |
| `["load_context", "classify", "decision_review", "collect"]` | 已进入审批字段收集 |
| `["load_context", "classify", "decision_review", "collect", "validate", "assignee"]` | 字段完整后获取审批节点，需要选择办理人/审批人 |
| `["load_context", "classify", "decision_review", "collect", "validate", "assignee", "preview"]` | 已生成提交前预览 |
| `["load_context", "classify", "decision_review", "submit"]` | 用户明确确认后提交审批 |

流程里有 `decision_review` 节点时，表示进入了有界决策复核。它用于接入模型复核，但必须有最大次数限制，避免无限重复思考。

前端联调时重点看响应里的：

- `awaiting_input`：当前应该渲染的控件。
- `answer`：下一轮请求里回传的结构化值。
- `awaiting_field_key` / `awaiting_field_label`：当前字段 key 和展示名。
- `trace`：本轮 graph 走过的节点。

运行时存储和性能：

- 会话状态支持 Redis：`{REDIS_PREFIX}ai_approval:session:{session_id}`，TTL 由 `AI_APPROVAL_SESSION_TTL_SECONDS` 控制。
- 远程模板、表单字段、动态下拉都有 TTL 缓存，分别由 `AI_APPROVAL_TEMPLATE_CACHE_TTL_SECONDS` 和 `AI_APPROVAL_DYNAMIC_OPTIONS_CACHE_TTL_SECONDS` 控制。
- CRM/ERP 调用会写 `crm.<接口>.timing` 日志，包含 `duration_ms`、`success`、`status_code` 和错误摘要。
- `_child` 控件组会展开必填子字段，并保留 `group_key`、`group_label`、`group_type`，用于后续复杂明细组装。

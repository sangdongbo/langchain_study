# LangGraph Studio 调试

## 启动

推荐用统一启动脚本。在 `.env` 中开启：

```text
AI_APPROVAL_STUDIO_ENABLED=true
AI_APPROVAL_STUDIO_HOST=127.0.0.1
AI_APPROVAL_STUDIO_PORT=2024
AI_APPROVAL_KILL_EXISTING_PORT_PROCESS=true
```

然后启动：

```powershell
cd D:\PythonProject\LearnOne\ai_approval_assistant
.\start_windows.ps1
```

脚本会后台启动 LangGraph Studio，本窗口继续前台运行 FastAPI。

如果测试服 Redis 不支持 RESP3，保持：

```text
REDIS_PROTOCOL=2
```

Windows 下 LangGraph CLI 读取自身资源时也需要 UTF-8 环境：

```text
PYTHONUTF8=1
PYTHONIOENCODING=utf-8
```

也可以只启动 Studio：

```powershell
cd D:\PythonProject\LearnOne\ai_approval_assistant
$env:PYTHONIOENCODING = "utf-8"
.\.venv\Scripts\langgraph.exe dev
```

Windows PowerShell 默认编码可能无法打印 LangGraph CLI 的图标字符，所以建议先设置 `PYTHONIOENCODING=utf-8`。

项目根目录的 `langgraph.json` 会加载：

```text
app.graph.studio:graph
```

环境变量来自 `.env`。如果本地不想连 Redis，可以临时设置：

```powershell
$env:AI_APPROVAL_SESSION_BACKEND = "memory"
```

## Studio 输入

Studio 直接调用 LangGraph state，不经过 FastAPI 的 `ChatRequest`。最小输入示例：

```json
{
  "session_id": "studio-new-purchase",
  "user_id": "U001",
  "uid": null,
  "authorization": null,
  "user_message": "我要申请采购笔记本电脑",
  "status": "idle",
  "intent": null,
  "approval_type": null,
  "collected_slots": {},
  "collected_values": {},
  "awaiting_field": null,
  "preview": null,
  "confirmed": false,
  "request_id": null,
  "approval_node": null,
  "approval_nodes": [],
  "selected_assignees": {},
  "assistant_message": "",
  "errors": [],
  "field_errors": [],
  "idempotency_key": null,
  "trace": [],
  "review_count": 0
}
```

更多示例在 `app/graph/studio.py`：

- `STUDIO_EXAMPLES["new_purchase"]`
- `STUDIO_EXAMPLES["new_expense"]`
- `STUDIO_EXAMPLES["resume_collecting"]`

写日志/日报也可以直接构造 state 调试：

```json
{
  "session_id": "studio-daily-report",
  "user_id": "863",
  "uid": "863",
  "authorization": "Bearer token",
  "user_message": "写今天日报",
  "status": "idle",
  "trace": []
}
```

顶层图里应能看到：

```text
daily_report_agent
```

默认“写日报/写日志”会统一路由到 `daily_report_agent`。展开日报子图后可以看到 `daily_report_action`、`load_daily_report_context`、`collect_daily_report_content`、`collect_daily_report_date`、`save_daily_report_draft`、`preview_daily_report`、`submit_daily_report` 等内部节点。

## Tools

ERP 能力封装在 `app/tools/approval_tools.py`，使用 `langchain_core.tools.tool`：

- `search_approval_templates`
- `get_approval_form_fields`
- `get_holiday_rule_options`
- `get_related_business_options`

日报能力封装在 `app/tools/daily_report_tools.py`：

- `load_daily_report_context`
- `save_daily_report_draft`
- `preview_daily_report_payload`
- `submit_daily_report_payload`

这些工具用于 Studio 和后续 agent 化调试；`/api/ai-approval/chat` 主流程也通过日报子图调用这些工具。

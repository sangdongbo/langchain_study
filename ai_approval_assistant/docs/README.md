# Graph 调试

导出 LangGraph 流程图：

```bash
.venv/bin/python ai_approval_assistant/scripts/export_graph.py
```

生成文件：

```text
ai_approval_assistant/docs/approval_graph.mmd
```

业务会话级流程图：

```text
ai_approval_assistant/docs/session_flow.mmd
```

可以把 `.mmd` 内容粘贴到 Mermaid Live Editor，或者在支持 Mermaid 的 Markdown 工具里查看。

接口返回里的 `trace` 可以和图对照看，例如：

```json
["load_context", "classify", "collect", "validate", "preview"]
```

这表示本轮从加载上下文开始，识别审批类型，收集字段，预校验，最后生成预览。

流程里有 `decision_review` 节点时，表示进入了有界决策复核。它用于后续接入模型复核，但必须有最大次数限制，避免无限重复思考。

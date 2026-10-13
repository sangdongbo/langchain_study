# 05 · 多轮对话与消息历史

第一轮记录数量与单价，第二轮只说「数量改成 6 台，单价不变」。模型需要看到第一轮
才能知道原来的单价。PydanticAI 支持显式 `message_history`，本课展示这种基础方式。

```powershell
uv run python examples/05_message_history/test.py
uv run python examples/05_message_history/run.py
```

`first.all_messages()` 返回当前会话完整历史；`first.all_messages_json()` 把历史编码
为 bytes；`ModelMessagesTypeAdapter.validate_json(...)` 恢复为框架消息对象。
第二轮使用 `agent.run_sync(..., message_history=history)`，不把历史拼成一个长字符串。

第二轮结果应包含 `6 × 68000 = 408000 元`。打印的 `new_messages()` 只属于第二轮，
`all_messages()` 包含传入的第一轮历史。测试另外在同一个 Agent 上不传历史发起运行，
验证它是一个独立会话；复用 Agent 对象本身不会自动保存这里的历史。

JSON 往返仅在内存中进行。本课展示的是对话上下文，不包含跨进程存储、长期记忆、
摘要或数据库 checkpoint。真实项目需要按认证用户/会话隔离历史，注意消息中可能包含
用户文本和工具返回值，并单独制定保留期限。

总价在这课由模型回答，用于说明上下文传递；需要程序保证金额正确时，结合第 03 课的
计算工具。离线模型只检查传入消息，因此能够明确区分「有历史」与「无历史」。

下一步：[06 · 流式输出](../06_streaming/README.md)。

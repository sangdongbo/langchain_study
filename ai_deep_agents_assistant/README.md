# AI Deep Agents Approval Assistant

这是 `ai_approval_assistant` 的 Deep Agents 版本示例。

原项目主要用 LangGraph 显式节点实现审批流程：

```text
加载上下文 -> 识别模板 -> 收集字段 -> 校验 -> 预览 -> 确认 -> 提交
```

这个版本保留同一类业务能力，但用 Deep Agents 的方式组织：

```text
Deep Agent
  -> 工具：查用户、查模板、收集草稿、生成预览、提交审批
  -> Checkpoint：按 session_id 保存线程状态
  -> Human-in-the-loop：提交审批前中断
```

## 功能

- `GET /health`
- `POST /api/ai-approval/chat`
- 支持请假、报销、采购 3 类审批模板
- 支持模板识别、字段抽取、缺字段追问
- 支持审批预览
- 用户明确“确认提交”后才恢复中断并提交
- 使用 `MemorySaver` 做 checkpoint
- 使用 `interrupt_on={"submit_approval_request": True}` 保护提交工具

## 启动

```powershell
cd ai_deep_agents_assistant
uv sync
.\start_windows.ps1 -Port 8020
```

或：

```powershell
cd ai_deep_agents_assistant
python -m uvicorn ai_deep_agents_assistant.app.main:app --host 127.0.0.1 --port 8020 --reload
```

需要在项目根目录或本目录 `.env` 中配置：

```text
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-chat
```

## 调用示例

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8020/api/ai-approval/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"session_id":"demo-001","user_id":"U001","message":"我要报销差旅费，金额 5200 元，因为去上海拜访客户，发票已提供"}'
```

当 Agent 准备提交时，会因为 `submit_approval_request` 被中断。

确认提交：

```powershell
Invoke-RestMethod `
  -Uri http://127.0.0.1:8020/api/ai-approval/chat `
  -Method Post `
  -ContentType "application/json" `
  -Body '{"session_id":"demo-001","user_id":"U001","message":"确认提交"}'
```

## 和 LangGraph 版的区别

| 项目 | `ai_approval_assistant` | `ai_deep_agents_assistant` |
| --- | --- | --- |
| 编排方式 | 显式 LangGraph 节点和条件边 | Deep Agent 自主调用工具 |
| 状态 | 自定义 `ApprovalState` | Deep Agents + checkpoint thread |
| 提交保护 | 代码守卫 | `interrupt_on` human-in-the-loop |
| 可控性 | 更强 | 更灵活 |
| 适合 | 生产强流程 | 学习 Deep Agents / 开放任务助手 |

真实生产建议：审批提交这种强约束流程仍建议 LangGraph 主控，Deep Agents 更适合做复杂意图理解、信息收集、报告和辅助决策。

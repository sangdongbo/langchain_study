# 飞书 MCP 工具

本例演示“外部飞书 MCP Server → MCPAdapter → Deep Agent”的完整链路。它参考
当前 Codex 宿主中可看到的 `mcp__lark_mcp__...` 工具，但不会尝试从 Python 进程
直接调用这些宿主工具。

## 先分清两种 MCP

| 位置 | 工具名称示例 | Python 项目能否直接调用 |
| --- | --- | --- |
| Codex 宿主进程 | `mcp__lark_mcp__docx_builtin_search` | 不能；这是 Codex 当前会话的内置连接 |
| 本示例 Python 进程 | 外部 Feishu MCP Server 返回的 `docx_builtin_search` 等工具 | 可以；通过 `MCPAdapter` 发现并调用 |

因此，系统 Codex 中的飞书连接只是本例的能力参考。项目运行时仍需要一个可通过
HTTP 访问的 Feishu MCP Server 地址和它要求的鉴权方式。

## 工具发现和安全边界

运行顺序如下：

```text
.env 的 FEISHU_MCP_URL
  -> MCPAdapter 连接 HTTP MCP Server
  -> list_tools() 动态发现工具
  -> 只保留飞书只读白名单
  -> create_deep_agent(tools=...)
  -> Agent 搜索文档并用中文总结
```

默认允许的只读工具后缀与系统 Codex MCP 的能力对应：

| 工具后缀 | 作用 |
| --- | --- |
| `docx_builtin_search` | 搜索飞书文档 |
| `docx_v1_document_rawContent` | 读取飞书文档正文 |
| `wiki_v1_node_search` | 搜索 Wiki 节点 |
| `wiki_v2_space_getNode` | 读取 Wiki 节点 |
| `im_v1_message_list` | 查询消息历史 |
| `bitable_v1_appTableRecord_search` | 查询多维表格记录 |

消息发送、Bitable 新增/更新、云盘权限修改等写操作默认会被过滤，例如：

```text
im_v1_message_create
bitable_v1_appTableRecord_create
bitable_v1_appTableRecord_update
drive_v1_permissionMember_create
```

这些工具会产生外部副作用，不能因为模型“需要一个工具”就自动开放。确实需要
调试全部工具时才临时设置 `FEISHU_MCP_ALLOW_ALL_TOOLS=true`，并且应在真实系统
中额外接入人工审批、操作审计和最小权限 Token。本例没有把写操作伪装成离线测试。

## 配置参数

在项目根目录执行：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`：

| 参数 | 必填 | 含义 |
| --- | --- | --- |
| `FEISHU_MCP_URL` | 是 | 外部 Feishu MCP Server 的 `http://` 或 `https://` 地址 |
| `FEISHU_MCP_HEADERS_JSON` | 否 | JSON 格式请求头，例如 `{"Authorization":"Bearer ..."}`；不要提交真实 Token |
| `FEISHU_MCP_ALLOW_ALL_TOOLS` | 否 | 默认 `false`，只启用只读白名单；临时设为 `true` 才开放全部发现工具 |
| `DEEPSEEK_API_KEY` / `LLM_API_KEY` | 是 | Deep Agent 使用的模型凭据，按项目根 README 的供应商优先级读取 |
| `LANGSMITH_TRACING` | 否 | 设为 `true` 且配置 Key 后，把 MCP 工具调用轨迹发送到 LangSmith |

`FEISHU_MCP_HEADERS_JSON` 的值会传给 FastMCP 的标准 `mcpServers` 配置，程序不会
打印其内容。不同飞书 MCP Server 可能使用 OAuth、Bearer Token 或宿主登录态，具体
鉴权字段以该 Server 的文档为准。

## 安装和启动

从本项目根目录执行：

```powershell
cd D:\PythonProject\LearnOne\deep_agent_examples
if (Get-Command deactivate -ErrorAction SilentlyContinue) { deactivate }
uv sync --extra mcp
.\.venv\Scripts\Activate.ps1
```

`mcp` 是可选依赖，不安装它不会影响其他专题。然后确认 `.env` 至少有：

```text
FEISHU_MCP_URL=https://你的飞书-mcp-server.example/mcp
DEEPSEEK_API_KEY=你的模型Key
```

启动真实示例：

```powershell
uv run python examples/feishu_mcp/run.py
uv run python examples/feishu_mcp/run.py --prompt "搜索研发采购制度并总结审批节点。"
```

终端会先打印 MCP 动态发现的工具名，再打印实际启用的只读工具、被过滤的写工具
和 Agent 最终总结。`thread_id` 可用于在 LangSmith 中定位本次运行；MCP Server
本身的服务端日志仍需到该 Server 所在环境查看。

## 离线测试

离线测试不导入 `MCPAdapter`，不会连接飞书、模型或 LangSmith：

```powershell
uv run python examples/feishu_mcp/test.py
```

预期输出：

```text
Feishu MCP 离线测试通过
- MCP 工具名称按后缀匹配，兼容 lark_/feishu_ 前缀
- 默认过滤消息发送等写操作
- Agent 完成文档搜索、正文读取和中文总结
```

这只能证明本地的工具白名单、Agent 工具循环和参数结构正确；它不代表真实的
飞书 URL、租户权限、Token 或网络连接已经配置成功。

## 常见问题

### `ModuleNotFoundError: fastmcp`

说明只安装了基础依赖。执行：

```powershell
uv sync --extra mcp
```

### `FEISHU_MCP_URL` 未配置

本例不会猜测或写死飞书地址。复制 `.env.example` 到 `.env`，填写 MCP Server
提供的 HTTP 地址。

### 发现了工具但全部被过滤

先检查 MCP Server 的实际工具名是否与系统 Codex 的能力后缀一致。默认过滤是有意
设计的；只有确认外部系统已接入写操作审批时，才临时打开 `FEISHU_MCP_ALLOW_ALL_TOOLS`。

### 在 LangSmith 中怎么看

配置有效 `LANGSMITH_API_KEY` 后，Trace 中会出现 `feishu-mcp-agent`，工具节点名称
对应 MCP Server 返回的工具名。系统 Codex 的 `mcp__lark_mcp__...` 调用属于 Codex
宿主会话，不会自动出现在这个 Python 项目的 LangSmith Trace 中；两者要通过工具名、
时间和输入输出内容进行对照。

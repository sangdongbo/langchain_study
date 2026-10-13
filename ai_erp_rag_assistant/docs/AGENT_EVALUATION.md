# Agent Evals

Agent Evals 用于检查修改 Prompt、模型或工作流后是否出现业务回归。评估复用实际
LangGraph 根图、领域子图、State 工具、字段校验、冻结预览和 Durable Execution
步骤重放逻辑，独立运行，不新增 HTTP 接口，不修改数据库表或现有业务配置。

## 运行方式

在项目根目录的 PowerShell 中执行默认离线回归：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_agent.py
.\.venv\Scripts\python.exe scripts/evaluate_agent.py --json
```

也可使用已有的 uv 环境：

```powershell
uv run python scripts/evaluate_agent.py --cases evals/agent_cases.example.jsonl --json
```

默认使用合成模型输出和模拟 ERP/知识库数据，关闭 LangSmith Trace 并禁止网络连接。
因此可以在没有 MySQL、Milvus 和 ERP 服务的情况下运行。线上接口不会加载该执行器；
执行器会临时替换全局工具，必须在独立进程中串行使用，不能挂到在线 HTTP 请求中。

需要衡量真实模型的路由、字段提取和回答效果时，显式执行：

```powershell
.\.venv\Scripts\python.exe scripts/evaluate_agent.py --with-llm --json
```

此模式使用现有 `.env` 的 LLM 配置，会产生模型调用费用；仍禁止数据库、真实 ERP 和
Milvus 连接，审批提交仍是模拟函数。`fixtures.plan`、`fixtures.extracted_fields` 和
`fixtures.answer` 在此模式不作为模型输出，期望路由仍独立评分。不需要修改
`ERP_WRITE_MODE` 或启动 API 服务。

退出码：`0` 全部通过，`1` 存在失败或运行异常，`2` 数据集路径或格式错误。
可直接作为 CI 的回归命令。JSON 报告包含模式、场景数、轮数、每项指标的分子/分母、
逐轮失败项和耗时；不输出完整答案、证据正文、表单值、Token 或原始异常消息。

## 案例集

`evals/agent_cases.example.jsonl` 每行一个场景，支持空行和 `#` 注释。示例身份固定为
公司 `16`、用户 `863`、人事部、权限标签 `employee`，全部为合成数据，不代表公司的
实际制度。每个场景从空状态开始；同一场景的多轮对话会恢复上一轮状态。

```json
{
  "id": "rag-no-evidence",
  "assistant_type": "rag",
  "turns": [{
    "message": "公司在火星出差补贴多少？",
    "fixtures": {"plan": {"route": "knowledge", "query": "火星出差补贴"}, "evidence": []},
    "expected": {
      "route": "knowledge",
      "tools": [{"name": "rag.search", "args": {"company_id": "16"}}],
      "should_answer": false,
      "citations": []
    }
  }]
}
```

上面的展示为了阅读展开了多行，写入 JSONL 时需压成一行。Fixtures 提供模拟输入，
expected 提供独立验收标准，不能从 expected 生成实际输出。客户查询可使用明确的
ISO 日期以避免运行日期变化；审批示例模板 `eval-leave` 只有必填的 `reason` 字段。

| 字段 | 作用 |
|---|---|
| `assistant_type` | `rag`、`approval` 或 `customer`，检查能力边界 |
| `turns[].message` | 本轮用户消息 |
| `user_id/company_id/department` | 模拟请求体字段，用于伪造身份隔离案例 |
| `fixtures.plan` | 离线模型计划：route、query、fields、decision 等 |
| `fixtures.answer/extracted_fields` | 离线回答和动态表单字段提取结果 |
| `fixtures.evidence/customer_items/approval_status` | 模拟检索或 ERP 返回数据 |
| `fixtures.write_mode` | 模拟提交返回 `mock` 或 `disabled`，不能设置 `remote` |
| `form_values` | 页面填写的审批字段，与自然语言提取共用真实校验 |
| `confirm` | 模拟明确确认输入 |
| `preview_confirmation` | `current` 回传当前预览、`stale` 回传旧哈希、`none` 不回传标识 |
| `replay` | 在内存步骤仓储上再次执行同一轮，检查工具和模型不重复调用 |

## 指标

| 指标 | 验收内容 |
|---|---|
| `route` | 最终路由符合期望；越界请求应被阻断并变为 general_chat |
| `tools` | 外部业务工具的名称、顺序、次数完全匹配，声明的参数逐项相等 |
| `identity` | 工具沿用可信公司和用户；检索还需沿用可信部门和权限标签 |
| `answer` | 非空回答，包含指定关键词，不包含指定禁词 |
| `workflow` | 审批追问、预览、取消、提交或写入关闭等状态正确 |
| `model_calls` | 可选检查规划、字段提取、回答调用；冻结预览确认不应再调用模型 |
| `no_answer` | `should_answer=false` 时明确表示无法确认或未查询到数据 |
| `citations` | 答案里的来源和页码符合期望，且每条都对应实际检索证据 |
| `replay` | 已完成步骤重放结果一致，工具和模型调用次数不增加 |

未声明的可选指标不计分；`tools: []` 表示不允许调用任何业务工具。工具名称为
`rag.search`、`erp.customer_activity`、`erp.approval_status`、`erp.approval_list`、
`erp.approval_template`、`erp.approval_submit`，与原接口审计名称是不同的观测层级。
运行异常会使整个场景失败，并计入对应指标分母，避免故障案例被跳过后虚增准确率。

离线通过只能证明确定性工作流在这些输入下没有回归，不能作为 LLM 路由准确率或真实
RAG 召回率。真实模型质量要用 `--with-llm`；真实召回/Rerank 继续使用现有
[RAG 评估](RAG_EVALUATION.md)。关键词规则不等同于完整语义正确性，需补充业务案例
并人工复核模型答案。当前只评估 LangGraph 编排，不覆盖 DeepAgent 父代理委派、SSE、
HTTP 登录校验、MySQL 断电恢复或真实 ERP 幂等性。

本功能不上传 LangSmith 数据集或实验；如后续接入，评估结果在 LangSmith Experiments
查看，Studio 用于图调试，二者用途不同。

# RAG 检索效果评测

评测模块用于回答“检索是否找对、Rerank 是否改善排序、无答案是否拒答、引用是否落在证据上”。
它是离线工具，不会创建数据库连接、写入 MySQL、修改 Milvus 数据或改变线上接口行为。

## 快速开始

先复制并修改样例集中的真实来源或 Chunk ID：

```powershell
Copy-Item .\evals\rag_cases.example.jsonl .\evals\rag_cases.jsonl
# 编辑 evals/rag_cases.jsonl，使 expected_sources/expected_chunk_ids 与实际文档一致
uv run python scripts/evaluate_rag.py --cases .\evals\rag_cases.jsonl
```

默认执行真实 Embedding + Milvus 检索和线上同一套 Rerank，但不调用答案 LLM。需要评估最终答案和引用时显式加上：

```powershell
uv run python scripts/evaluate_rag.py --cases .\evals\rag_cases.jsonl --with-llm --json
```

`--with-llm` 会产生模型调用费用；`--no-rerank` 可以作为向量原始排序的对照组。
评测失败时脚本返回退出码 `1`，可用于 CI 门禁。

## JSONL 样例格式

每行一个 JSON 对象，支持字段：

```json
{
  "id": "employee_handbook_leave",
  "query": "病假需要什么材料？",
  "company_id": "16",
  "knowledge_base_key": "employee_handbook",
  "department": "公共制度",
  "permission_tags": ["knowledge:employee_handbook"],
  "expected_chunk_ids": ["16:employee_handbook:..."],
  "expected_sources": ["员工手册.pdf"],
  "expected_citations": [{"source": "员工手册.pdf", "page": 9}],
  "should_answer": true,
  "top_k": 5
}
```

`expected_chunk_ids` 优先用于计算 Recall；没有 Chunk ID 时才使用 `expected_sources`。
可回答样例必须配置其中一个。无答案样例设置 `should_answer=false`，并且不能配置期望文档。
`company_id`、部门和权限标签会逐条传入检索器，评测集不能用一条身份覆盖所有租户。

## 指标口径

| 指标 | 计算方式 |
|---|---|
| `recall_at_k` | 期望 Chunk/来源中被前 K 条检索结果命中的比例 |
| `retrieval_hit_rate` | 可回答样例是否至少命中一个期望结果 |
| `mean_reciprocal_rank` | 第一条期望结果排名的倒数平均值 |
| `rerank_top1_accuracy` | Rerank 后第一条是否为期望结果 |
| `no_answer_rejection_rate` | `should_answer=false` 且检索结果为空的比例 |
| `no_answer_abstention_rate` | 使用 `--with-llm` 时，无答案样例明确说明没有依据/无法确认的比例 |
| `citation_precision` | 答案引用中同时匹配证据来源和页码的比例 |
| `expected_citation_recall` | 配置 `expected_citations` 时，期望来源/页码被答案引用的比例 |

单条样例只有在可回答样例 Recall=1、无答案样例结果为空，并且（启用 `--with-llm` 时）所有引用都能在证据中找到，才算通过。
报告中的 `error_cases` 与 `failed_cases` 会区分外部服务错误和质量未达标。

## 建议的评测集

至少准备三类问题：

1. 业务制度问题：有明确来源文件和页码，检查召回、Rerank 和引用。
2. 相邻制度问题：关键词相似但答案属于另一章节，检查 Rerank 是否把正确章节排到前面。
3. 无答案问题：知识库没有依据，检查检索阈值和回答是否明确拒答。

每次修改切分、Embedding、Milvus 阈值、Rerank 或 Prompt 后重新运行，并把 JSON 报告留在 CI 构建产物中。生产环境建议按知识库分别维护评测集，避免跨公司混用期望来源。

## 先评测，再决定检索方案

先用同一份评测集分别跑向量原始排序和当前 Rerank，两个报告只允许检索排序策略不同：

```powershell
uv run python scripts/evaluate_rag.py --cases .\evals\rag_cases.jsonl --no-rerank --json > .\evals\report.vector.json
uv run python scripts/evaluate_rag.py --cases .\evals\rag_cases.jsonl --json > .\evals\report.rerank.json
```

建议按以下顺序判断，避免在没有业务数据时直接增加模型或检索依赖：

| 观察结果 | 下一步建议 |
|---|---|
| `recall_at_k` 或 `retrieval_hit_rate` 偏低，原始向量和 Rerank 都召回不到正确来源 | 先优化 Chunk、Embedding 或加入 BM25/关键词混合召回；Rerank 不能修复候选集缺证据 |
| 召回率正常，但 `rerank_top1_accuracy` 明显高于 `--no-rerank` | 保留当前 Rerank；候选量和模型成本达到瓶颈后再评估专用 Rerank 模型 |
| 召回率正常，但 Rerank 与原始排序几乎没有差异 | 暂不引入专用 Rerank，优先减少一次 LLM 调用或调整候选数量 |
| `no_answer_rejection_rate` 或 `no_answer_abstention_rate` 偏低 | 先调 `RAG_MIN_SCORE`、证据为空拒答规则和 Prompt，不要用更多召回掩盖无答案问题 |
| `citation_precision` 偏低或 `expected_citation_recall` 偏低 | 先检查来源/页码元数据和引用拼接，再考虑模型升级 |

当前项目没有启用 BM25/关键词混合检索，也没有接入专用 Rerank 模型；这两个方向应在报告显示
瓶颈后再作为独立实验分支接入，并继续用同一评测集对比，不能只凭主观问答体验决定。

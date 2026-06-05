# AI 工程面试问答整理

本文档整理截图中出现的面试题，按 RAG、Spring AI、Agent、MCP 和多智能体归类。问题和答案分开保存，便于面试前快速复习。

## 一、RAG 与模型私有化

### 1. 你之前的项目做过模型的私有化部署吗？

可以这样回答：

做过或了解过私有化部署。私有化部署的核心不是只把模型跑起来，而是把模型服务、推理框架、权限、日志、监控和业务系统打通。常见方案是用 vLLM、TGI、Ollama、LMDeploy 或厂商推理服务部署模型，通过 OpenAI 兼容接口暴露给业务。业务侧再接入 RAG、Agent 或工作流。

回答时可以补充：

- 模型部署：GPU 资源、量化、并发、上下文长度。
- 服务接口：OpenAI-compatible API、鉴权、限流。
- 数据安全：私有知识库不出内网，日志脱敏。
- 运维：监控延迟、吞吐、显存、失败率。

如果没有实际做过，可以说：

我没有完整负责过生产私有化部署，但理解部署链路，并在本地或测试环境跑过模型服务。生产落地时我会重点关注模型选型、推理服务、网关鉴权、监控和业务 RAG 接入。

### 2. RAG 项目中为什么需要向量数据库？

向量数据库负责保存文本块的向量、原文和元数据，并在用户提问时快速找出语义最相近的内容。普通数据库擅长精确查询，向量数据库擅长相似度查询。RAG 需要先检索相关上下文，再让模型基于上下文回答，所以向量数据库是知识库检索层的核心组件。

### 3. RAG 答案不准确通常怎么排查？

优先按链路排查：

1. 数据是否正确入库，文本是否乱码或缺失。
2. 切片是否合理，标题和上下文是否丢失。
3. Embedding 模型是否适合中文和业务领域。
4. 检索参数是否合适，例如 `top_k`、过滤条件、相似度阈值。
5. 是否需要 rerank。
6. Prompt 是否要求基于资料回答，没有依据就说不知道。
7. 是否返回来源，便于定位是检索错还是生成错。

## 二、Spring AI 与 Spring AI Alibaba

### 4. Spring AI 与 Spring AI Alibaba 的区别是什么？

Spring AI 是 Spring 官方推出的 AI 应用开发框架，目标是给 Java/Spring 项目提供统一的模型调用、Prompt、Embedding、VectorStore、Tool Calling、RAG 等抽象。

Spring AI Alibaba 是阿里生态对 Spring AI 的扩展和适配，通常更关注通义千问、百炼、DashScope、Nacos、RocketMQ、Sentinel 等阿里云或阿里中间件生态集成。

简单对比：

| 对比项 | Spring AI | Spring AI Alibaba |
| --- | --- | --- |
| 定位 | Spring 官方 AI 抽象框架 | 面向阿里生态的增强与集成 |
| 重点 | 通用模型和向量库抽象 | 通义、百炼、云产品和国内生态 |
| 使用场景 | 标准 Spring AI 应用 | 阿里云/通义体系内落地 |

## 三、Workflow、Agent 与 ReAct

### 5. Workflow 和 Agent 最大的区别是什么？

Workflow 是预先设计好的流程，步骤、分支和执行顺序通常由开发者定义。Agent 是目标驱动的智能体，模型可以根据当前任务自主决定下一步、选择工具、观察结果并继续执行。

| 对比项 | Workflow | Agent |
| --- | --- | --- |
| 控制权 | 开发者控制流程 | 模型参与决策 |
| 路径 | 相对固定 | 可动态变化 |
| 稳定性 | 更可控 | 更灵活但更难约束 |
| 适合场景 | 审批、ETL、固定业务流程 | 开放问答、工具选择、复杂任务拆解 |

工程里常把两者结合：外层用 Workflow 保证边界和审批，内部某些节点使用 Agent 做动态决策。

### 6. Agent 的 ReAct 机制是什么？

ReAct 是 Reasoning and Acting 的缩写，表示 Agent 在推理和行动之间循环。

典型过程：

```text
Thought: 分析当前问题
Action: 选择一个工具
Observation: 读取工具返回结果
Thought: 根据观察继续推理
Action: 可能再次调用工具
Final Answer: 给出最终回答
```

ReAct 的价值是让模型不是一次性回答，而是可以边想边查、边执行边修正。风险是步骤可能过多、工具可能误用，所以要通过工具描述、系统提示词、最大轮数、权限控制和日志观测来约束。

## 四、MCP 与 Agent

### 7. MCP 如何和 Agent 结合？

MCP 可以理解为给 Agent 提供工具和上下文的标准协议。Agent 本身负责理解任务和决策，MCP Server 负责暴露可调用能力，例如文件系统、数据库查询、浏览器、企业内部系统、搜索服务等。

结合方式：

```text
Agent
-> 读取 MCP 工具列表
-> 根据工具描述选择工具
-> 按 schema 传参调用 MCP Server
-> 获取结果
-> 继续推理或生成最终答案
```

好处：

- 工具接入标准化。
- Agent 不需要直接知道每个系统的私有 SDK。
- 权限、审计和工具边界更容易管理。

## 五、多 Agent

### 8. Multi-Agent 是什么？

Multi-Agent 是多个智能体协作完成任务的模式。通常会有一个主 Agent 或调度器接收用户请求，再把子任务分配给不同 Subagent，最后汇总结果。

典型结构：

```text
User Request
-> Main Agent
-> Subagent A / Subagent B / Subagent C
-> Main Agent 汇总
-> Response
```

不同子 Agent 可以有不同角色，例如检索专家、代码专家、数据分析专家、审核专家。

### 9. 多 Agent 相比单个 Agent 的优势在哪？

优势：

- 分工更清楚，每个 Agent 只关注一个专业方向。
- 复杂任务可以并行处理，提高效率。
- 可以加入审核 Agent，降低错误率。
- 不同 Agent 可以使用不同工具、模型和 Prompt。

代价：

- 编排复杂度更高。
- 成本和延迟可能增加。
- 多个 Agent 的结论可能冲突，需要仲裁机制。
- 需要更好的日志、状态和权限控制。

### 10. Agent Skills 和 Multi-Agent 有什么区别？

Agent Skills 是给同一个 Agent 加载能力包，让它具备某类专业知识、工具或任务模板。Multi-Agent 是多个 Agent 协作，每个 Agent 可以有独立角色、上下文和工具。

简单理解：

```text
Agent Skills: 一个 Agent 装不同扩展包。
Multi-Agent: 多个 Agent 分工协作。
```

| 对比项 | Agent Skills | Multi-Agent |
| --- | --- | --- |
| 粒度 | 能力模块 | 协作主体 |
| 运行方式 | 通常仍由一个 Agent 决策 | 多个 Agent 互相调用或被调度 |
| 适合场景 | 给 Agent 增加专业能力 | 复杂任务拆解、并行、审核 |

### 11. 什么是 Harness？

Harness 在 AI 工程语境中通常指“测试、评估和运行框架”。它不是单一固定产品名，而是一套用来稳定运行和评估 Agent/RAG/模型应用的工程外壳。

常见能力：

- 准备测试集和标准答案。
- 批量运行模型、RAG 或 Agent。
- 记录输入、输出、工具调用和耗时。
- 根据规则或评估模型打分。
- 对比不同 Prompt、模型、检索参数和版本。

一句话：Harness 是把 AI 应用从“能跑一次”变成“可重复评估、可回归测试、可上线监控”的工程化支撑。

## 六、面试回答原则

- 先给定义，再讲区别，最后落到工程实践。
- 能说链路就说链路，例如“加载 -> 切片 -> 向量化 -> 入库 -> 检索 -> 重排 -> 生成”。
- 遇到没做过的内容，不要硬编生产经验，可以说“了解链路，在测试环境做过，生产会重点关注哪些风险”。
- Agent 相关问题要主动提到工具边界、权限、最大轮数、日志和可观测性。

## 七、大模型简历怎么写

截图里给出的方向可以整理成一套更稳妥的简历策略。

### 12. 有多年 Java 工作经验，怎么投大模型岗位？

不要把自己包装成“算法研究员”，而是突出“AI 工程化落地”。Java 背景的优势是业务系统、工程质量、后端接口、权限、日志、部署和数据链路。

简历关键词：

- Java / Spring Boot / Spring AI / LangChain4j。
- RAG、向量数据库、Milvus、Elasticsearch、BM25。
- 企业知识库、智能客服、ERP/CRM 智能助手。
- 工具调用、MCP、Agent 编排、多 Agent 协作。
- 模型接入、OpenAI-compatible API、DeepSeek/Qwen/GLM。

项目描述模板：

```text
负责企业知识库问答系统后端开发，接入大模型 OpenAI 兼容接口；实现文档解析、切片、Embedding、Milvus 向量检索、BM25 混合检索和答案来源追溯；结合业务权限做多租户过滤，并通过日志和评测集持续优化回答准确率。
```

### 13. 有多年编程经验但不是 Java，怎么投？

主投“大模型应用工程师 / AI 应用开发 / Agent 工程师”。重点是能把模型接入真实系统，而不是只会调 API。

需要准备：

- 至少 2-3 个可讲清楚的 AI 项目。
- 一个 RAG 项目，能讲清楚数据、切片、检索、重排、评估。
- 一个 Agent 项目，能讲清楚工具调用、状态管理、权限边界。
- 会读 Python 生态代码，了解 FastAPI、LangChain、LangGraph、Milvus/Chroma。

### 14. 应届生或转行，没有生产项目怎么办？

主投实习或初级 AI 应用开发岗位，但项目要做深一点。不要只做“上传 PDF 问答”，要做成可展示、可复盘、可评估的项目。

推荐组合：

1. RAG 项目：PDF/Markdown/图片解析 + 混合检索 + rerank + 来源展示。
2. Agent 项目：工具调用 + 子 Agent + 长期记忆 + 人工确认。
3. 算法或微调补充：Embedding/Reranker 微调、LoRA/SFT、评估集构建。

简历写法：

```text
独立实现多模态 RAG 学习项目，支持 PDF、Markdown 和图片 OCR 解析；使用标题递归切片和语义切片对比检索效果；基于 Milvus 建立 dense/sparse 双字段索引，使用 BM25 + 向量检索 + Reranker 进行召回和精排；构建 100 条问答评测集，对比 Recall@5、MRR 和最终回答准确率。
```

## 八、最近笔试和面试变化

截图里总结得很贴近当前岗位趋势，可以按下面这几类准备。

### 15. 最近笔试和面试更爱问什么？

1. 数据结构和算法仍然是基础，大约占不少岗位的主线笔试内容。链表、栈队列、哈希、二叉树、图、动态规划、排序、TopK 都要会。
2. Agent 问题变多，尤其是多 Agent 架构、Supervisor、工具调用、handoff、状态和记忆。
3. 评估问题变多，包括 RAG 评估、Agent 评估、模型评估。
4. 切片和向量数据库问题变多，例如 chunk size 怎么选、Milvus schema 怎么设计、索引怎么选。
5. 上下文工程变多，例如长上下文、摘要记忆、上下文压缩、上下文隔离。
6. Rerank 会被问到，尤其是为什么需要 rerank、放在哪一层、怎么评估效果。
7. 工程化方案变多，例如缓存、异步、权限、日志、降级、成本控制。
8. 应用开发也会问算法，但多停留在理解和应用层。
9. 应用开发偶尔问 PyTorch，主要是张量、模型推理、显存、微调基础。
10. 研发工程师岗位一定会问算法、PyTorch、训练/微调、分布式和论文。

### 16. 面试官问 RAG 项目，最佳回答结构是什么？

建议用 7 层回答：

1. 业务背景：解决什么问题，用户是谁，数据是什么。
2. 数据处理：PDF、Word、Markdown、图片、表格怎么解析。
3. 切片策略：为什么这么切，怎么保留标题和元数据。
4. 检索策略：向量检索、BM25、metadata filter、Hybrid Search。
5. 重排和生成：reranker、Prompt、引用来源、拒答。
6. 评估优化：Recall@K、MRR、人工评测集、错误分析。
7. 工程化：权限、多租户、缓存、监控、日志、成本。

一个完整回答示例：

```text
这个项目不是简单的 PDF 问答，而是企业内部知识库。我的主要工作是把文档从解析到问答闭环做起来。数据层支持 PDF、Markdown 和图片 OCR，切片时先按标题层级切，再对过长段落递归切分，并把文档名、章节、页码写入 metadata。检索层用了 Milvus，设计了 dense 向量字段和 sparse/BM25 字段，先做 hybrid search，再用 reranker 精排，最后只把高相关片段放入 Prompt。生成层要求模型必须基于引用回答，不足时拒答。评估上我做了业务问题集，分别看 Recall@5、MRR 和端到端答案正确率。
```

## 九、Agentic RAG 与 DeepAgents

### 17. 什么是 Agentic RAG？

Agentic RAG 是把 Agent 引入 RAG 流程。传统 RAG 通常是“一次检索 + 一次生成”，Agentic RAG 可以让 Agent 自主决定检索策略和工具调用。

它可以做：

- 改写用户问题。
- 拆解多跳问题。
- 选择知识源：向量库、BM25、图谱、Web、SQL、API。
- 判断证据是否足够。
- 不足时继续检索或追问。
- 最终生成带引用的答案。

面试中可以这样讲：

```text
Agentic RAG 的核心不是把 RAG 和 Agent 简单拼在一起，而是让 Agent 参与检索决策。比如它可以先判断问题是否需要查内部知识库，检索后再判断证据是否充分；如果不足，就改写 query、切换 BM25 或调用业务 API。这样能处理传统线性 RAG 不擅长的多跳问题和动态工具问题。
```

### 18. DeepAgents 框架是什么？

LangChain 的 Deep Agents 文档把 deep agent 看成一套更完整的 agent harness：不仅有模型和工具，还包括长任务执行所需的文件系统、记忆、技能、子 Agent、上下文管理、人类审批、流式和持久执行。

它强调的能力包括：

- 工具和环境：读写文件、执行代码、调用工具。
- 数据连接：按需加载 memory、skills、domain knowledge。
- 上下文管理：长任务中总结历史、隔离大工具输出。
- 子 Agent：把复杂任务委托给专业 subagent，保持主 Agent 上下文干净。
- 人在回路：关键步骤暂停等待审批。
- 运行时：基于 LangGraph，支持 durable execution、streaming、human-in-the-loop。

如果被问 DeepAgents 和普通 ReAct Agent 区别：

```text
普通 ReAct Agent 更像一个工具调用循环；DeepAgents 更像一套长任务智能体工程框架。它把 planning、filesystem、memory、skills、subagents、human approval 和 context engineering 都变成框架能力，适合复杂、长周期、多步骤任务。
```

## 十、Harness Engineering

### 19. Harness Engineering 到底是什么？

Harness Engineering 可以理解为“围绕模型外部的一整套工程驾驭层”。模型只负责思考和生成，Harness 负责让它稳定、安全、可控地执行复杂任务。

可以用一句公式：

```text
Agent = Model + Harness
```

其中 Model 负责推理和决策；Harness 负责工具、记忆、规则、安全护栏、执行循环、状态管理、权限、人类审批、日志、评估和恢复。

面试回答：

```text
Harness Engineering 解决的是 Agent 工程稳定性问题。传统 Agent 在长任务中容易上下文膨胀、状态丢失、工具乱调、失败后无法恢复。Harness 会把任务规划、文件系统、记忆、工具权限、审批、日志、评估、异常恢复封装成一套运行框架，让 Agent 从“能跑一次”变成“能稳定跑长任务”。
```

### 20. DeepAgents 里有哪些 Harness 能力？

可以按模块回答：

| 模块 | 能力 | 价值 |
| --- | --- | --- |
| Planning | `write_todos` 维护任务清单 | 长任务可追踪、可恢复 |
| Virtual Filesystem | `ls/read_file/write_file/edit_file/glob/grep` | 降低上下文膨胀，文件作为外部记忆 |
| Subagents | 通过 `task` 委托专业 Agent | 上下文隔离，专业分工 |
| Memory | 保存用户偏好、历史结论、项目状态 | 长期任务连续性 |
| Skills | 加载特定领域能力包 | 复用专业流程和工具 |
| Middleware | 压缩对话、拦截工具、加日志 | 稳定性、可观测性和成本控制 |
| Human-in-loop | 关键操作前审批 | 降低高风险动作 |
| Sandboxes | 隔离执行环境 | 安全运行代码和工具 |

## 十一、OpenAI Agents SDK 和 MCP 怎么回答

### 21. OpenAI Agents SDK 现在主要提供什么？

OpenAI Agents SDK 是 OpenAI 官方的 Python Agent SDK。官方文档把核心抽象概括为：Agents、Agents as tools / Handoffs、Guardrails，并提供 tracing、MCP server tool calling、function tools、sandbox agents 等能力。

面试里可以这样说：

```text
OpenAI Agents SDK 的特点是抽象少、Python-first、内置 agent loop。Agent 可以带 instructions 和 tools；handoff 可以把任务交给其他 Agent；guardrails 做输入输出校验；tracing 用来观察和调试工具调用链。它适合快速构建生产级 Agent 应用。
```

### 22. MCP 在 Agent 工程里为什么重要？

MCP 解决的是工具接入标准化。以前每个系统都要写一套私有 SDK 和工具包装，现在可以把文件、浏览器、数据库、企业系统、搜索等能力封装为 MCP Server，由 Agent 统一发现和调用。

回答重点：

- MCP 不等于 Agent，它是工具和上下文协议。
- Agent 负责决策，MCP Server 负责提供工具。
- 工程价值是标准化、权限边界、可审计、可复用。

## 十二、RAG/Agent 简历项目升级清单

如果已有一个基础 RAG 项目，可以按下面顺序升级：

1. 文档解析：增加 PDF、Markdown、图片 OCR、表格处理。
2. 切片：从固定切片升级为标题递归切片和 Parent-Child。
3. 元数据：增加文档名、页码、标题路径、租户、权限字段。
4. 检索：增加 Milvus dense + sparse/BM25 hybrid search。
5. 融合：增加 WeightedRanker 或 RRF。
6. 精排：增加 BGE/Qwen reranker。
7. 生成：回答附引用，不足拒答。
8. 评估：构建 100 条问题集，记录 Recall@K、MRR、答案正确率。
9. Agentic：让 Agent 自动选择检索源、改写 query、判断证据是否足够。
10. 工程化：缓存、异步入库、日志、权限、多租户、监控。

## 十三、当前资料索引

- [Milvus 官方文档：Full Text Search](https://milvus.io/docs/full-text-search.md)、[Hybrid Search](https://milvus.io/docs/hybrid_search_with_milvus.md)、[Reranking](https://milvus.io/docs/reranking.md)。
- [智谱 AI 文档：上下文增强技术报告](https://docs.bigmodel.cn/cn/guide/tools/knowledge/contextual)。
- [Anthropic Research：Contextual Retrieval](https://www.anthropic.com/research/contextual-retrieval)。
- [LangChain：Deep Agents](https://www.langchain.com/deep-agents)。
- [OpenAI：Agents SDK](https://platform.openai.com/docs/guides/agents-sdk/) 和 [OpenAI Agents SDK Python 文档](https://openai.github.io/openai-agents-python/agents/)。
- [Hugging Face：BAAI bge-reranker-large](https://huggingface.co/BAAI/bge-reranker-large)。
- [ModelScope：GME-Qwen2-VL 多模态 embedding](https://modelscope.cn/models/iic/gme-Qwen2-VL-2B-Instruct)。
- [Qwen 官方：Qwen3 Embedding 与 Reranker](https://qwenlm.github.io/blog/qwen3-embedding/)。
- arXiv：Agentic RAG、Multimodal RAG、Reasoning Agentic RAG 等综述和技术报告。

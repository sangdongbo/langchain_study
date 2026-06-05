# Python RAG 常用知识点整理

本文档整理截图中的 RAG 原理、数据加载与切片、Embedding、向量库、Milvus 检索和高级 RAG 方向。它和 `python_langchain_notes.md` 分开保存：LangChain 笔记保留框架组件总览，这里专门用于复习 RAG 项目链路。

整理原则：

- RAG 内容集中保存，便于从“数据准备 -> 检索 -> 生成 -> 优化”顺序复习。
- Milvus 细节只保留和 RAG 直接相关的部分；完整 Milvus 架构、字段、索引和部署见 `python_milvus_notes.ipynb`。
- 示例优先使用离线可运行代码，不强制调用外部模型、向量库服务或数据库。

## 一、RAG 是什么

RAG 是 Retrieval-Augmented Generation，中文常译为“检索增强生成”。核心思路是：模型回答前先从外部知识库检索相关资料，再把资料作为上下文交给大语言模型生成答案。

普通 LLM 问答：

```text
用户问题 -> LLM -> 回答
```

RAG 问答：

```text
用户问题 -> 检索知识库 -> 取回相关片段 -> 组装 Prompt -> LLM -> 回答
```

RAG 解决的主要问题：

| 问题 | RAG 的作用 |
| --- | --- |
| 模型知识过期 | 接入最新业务文档、网页、制度、代码库 |
| 幻觉严重 | 要求模型基于检索证据回答 |
| 私有知识无法训练进模型 | 通过外部知识库临时注入上下文 |
| 回答不可追溯 | 返回来源文件、页码、段落、链接 |

RAG 不等于“万能知识库”。如果检索不到、切片不合理、Embedding 不适配、Prompt 约束不够，答案仍然会差。

## 二、RAG 的完整链路

截图中的 RAG 原理图可以拆成两条链路：数据准备和查询生成。

### 1. 数据准备链路

```text
本地文件 / 网页 / 数据库
-> Document Loader
-> 文本清洗
-> Text Splitter
-> Text Chunks
-> Embedding
-> VectorStore
```

各组件职责：

| 组件 | 作用 | 常见工具 |
| --- | --- | --- |
| Document Loader | 读取 PDF、Word、Markdown、HTML、数据库记录 | Tika、Unstructured、PyPDF、Docx2txt |
| 文本清洗 | 去掉页眉页脚、乱码、重复空白、无意义符号 | 自定义函数 |
| Text Splitter | 把长文本切成适合检索的小块 | RecursiveCharacterTextSplitter |
| Embedding | 把文本转成向量 | OpenAI、BGE、Qwen Embedding、Jina |
| VectorStore | 存储向量、文本和元数据 | Milvus、Chroma、FAISS、Elasticsearch |

### 2. 查询生成链路

```text
用户问题
-> Query Embedding
-> 向量相似度检索
-> 取回相关文本块
-> Prompt Template
-> LLM
-> Answer
```

关键点：

- 用户问题也要转成向量，才能和知识库里的文本向量做相似度比较。
- 检索阶段通常返回 `top_k` 个片段，例如 3、5、10 个。
- Prompt 中要明确“只根据上下文回答；没有依据就说不知道”。
- 最终回答最好带来源，便于排查检索是否正确。

## 三、数据加载和切片

截图中提到的 RAG 项目数据加载与切片，重点包括 Tika、解析器选择、Markdown 结构化解析和按语义切割。

### 1. Tika DocumentReader 是什么

Apache Tika 是一个文档内容解析工具，可以从 PDF、Word、PPT、HTML、图片 OCR 等文件里提取文本和元数据。RAG 项目里常把它封装成 DocumentReader 或 Loader。

适合场景：

- 文件格式很多，不想给每种格式单独写解析器。
- 需要从办公文档中提取纯文本。
- 先快速搭建“能读大多数文件”的知识库导入流程。

局限：

- 对复杂 PDF、扫描件、表格、分栏排版的还原不一定理想。
- 提取结果通常需要二次清洗。
- 对 Markdown、代码、结构化文档，专用解析器往往更准确。

### 2. 解析器选择建议

| 文件类型 | 推荐方式 | 说明 |
| --- | --- | --- |
| Markdown | MarkdownHeaderTextSplitter 或自定义标题解析 | 保留标题层级，适合知识库 |
| 简单 PDF | PyPDF / pdfplumber | 轻量、易集成 |
| 复杂 PDF | Unstructured / Tika / OCR | 更强但更重 |
| Word | docx2txt / Unstructured / Tika | 先提取段落和标题 |
| HTML | BeautifulSoup / UnstructuredHTMLLoader | 去掉导航、广告、脚本 |
| 数据库记录 | 直接映射为 Document | 元数据要保留主键和业务字段 |

### 3. 切片策略

切片的目标是让每个 chunk 既包含完整语义，又不会太长。

常见参数：

| 参数 | 含义 | 常见取值 |
| --- | --- | --- |
| `chunk_size` | 单个文本块最大长度 | 300-1000 中文字符，或 500-1500 tokens |
| `chunk_overlap` | 相邻文本块重叠长度 | `chunk_size` 的 10%-20% |
| separator | 优先切割符 | 标题、段落、句号、换行 |

经验：

- FAQ、制度条款、API 文档适合按标题切。
- 长篇文章适合先按标题，再按段落和长度递归切。
- 代码文档适合按函数、类、标题切，不能只按固定长度硬切。
- 表格数据应尽量保留表头，否则单行检索回来会丢含义。

## 四、Embedding 与向量库

Embedding 把文本映射到向量空间。语义接近的文本，向量距离通常更近。

常见向量类型：

| 类型 | 说明 |
| --- | --- |
| 稠密向量 | 最常见，适合语义相似度检索 |
| 稀疏向量 | 类似关键词权重，适合 BM25、关键词增强 |
| 二进制向量 | 占用空间小，适合部分高性能场景 |

向量库通常保存：

- 主键，例如 `id`。
- 向量字段，例如 `embedding`。
- 原文片段，例如 `text`。
- 元数据，例如 `source`、`page`、`title`、`tenant_id`、`created_at`。

## 五、Milvus 在 RAG 中负责什么

Milvus 是向量数据库，RAG 中主要负责存储和检索。

典型职责：

- 保存 chunk 的向量、正文和元数据。
- 根据用户问题向量做相似度搜索。
- 支持标量过滤，例如按租户、来源、时间、标签筛选。
- 通过索引提升大规模向量搜索性能。

Milvus 和 LangChain 的关系：

```text
LangChain: Loader / Splitter / Embedding / Retriever / Chain 编排
Milvus: VectorStore，负责向量写入、索引、检索和过滤
LLM: 根据检索上下文生成回答
```

## 六、检索方式

截图中的 Milvus 检索脑图可整理为以下类别。

| 检索方式 | 说明 | 适合场景 |
| --- | --- | --- |
| 基本向量搜索 | 只按向量相似度取 top_k | 普通语义问答 |
| 过滤搜索 | 向量检索 + 元数据条件 | 多租户、按文件、按权限 |
| 范围搜索 | 只返回距离或分数在阈值内的结果 | 需要设置水位线 |
| 分组搜索 | 按字段分组后返回结果 | 同一文件不想占满结果 |
| 主键搜索 | 按 id 查询 | 调试、回溯来源 |
| 混合搜索 | 稠密向量 + 稀疏向量 / BM25 | 语义和关键词都重要 |
| 全文搜索 | 关键词倒排检索 | 专有名词、编号、短文本 |
| 文本匹配 | 按字符串字段过滤 | 标签、类别、状态 |

RAG 项目里常用组合：

```text
用户问题 -> 向量检索 top_k=20 -> 元数据过滤 -> rerank -> 取前 3-5 个片段 -> 生成回答
```

## 七、索引与水位线

索引用来加速向量检索。不同索引适合不同数据规模、延迟和召回要求。

常见索引：

| 索引 | 特点 |
| --- | --- |
| FLAT | 暴力搜索，召回高，数据小时简单可靠 |
| IVF_FLAT / IVF_SQ8 | 聚类后搜索，适合中大规模数据 |
| HNSW | 图索引，召回和延迟表现好，内存占用较高 |
| DiskANN | 面向更大规模和磁盘场景 |
| AUTOINDEX | Milvus 自动选择和管理索引策略 |

水位线可以理解为检索结果的最低可信门槛，例如相似度低于某个阈值就不返回。它能减少“硬凑上下文”的情况。

设置水位线时要注意：

- 阈值太高：容易检索不到资料。
- 阈值太低：会把不相关片段塞进 Prompt。
- 最好结合业务问题集做评估，而不是凭感觉设置。

## 八、高级 RAG 方向

截图中提到的高级 RAG 可以按优化目标归类。

| 方向 | 解决的问题 | 核心思路 |
| --- | --- | --- |
| Query Rewrite | 用户问题表达不清 | 先改写问题再检索 |
| Multi Query | 单一问题向量召回不足 | 生成多个查询并合并结果 |
| Rerank | top_k 结果顺序不准 | 用重排模型重新打分 |
| Corrective RAG | 检索结果不可靠 | 判断结果质量，不足则补检索或改写 |
| Adaptive RAG | 不同问题走不同策略 | 简单问题少检索，复杂问题多步骤 |
| Agentic RAG | 需要工具和决策 | Agent 决定检索、调用工具或追问 |
| Graph RAG | 实体关系很重要 | 构建知识图谱辅助检索 |
| Multimodal RAG | 图片、表格、文本混合 | 文本向量和多模态向量联合检索 |

## 九、RAG 项目排查清单

| 现象 | 优先检查 |
| --- | --- |
| 检索结果为空 | 数据是否入库、collection 名是否一致、过滤条件是否过严 |
| 检索结果不相关 | 切片是否太碎、Embedding 是否适合中文、top_k 是否太小 |
| 答案编造 | Prompt 是否要求基于上下文、是否允许“不知道” |
| 答案遗漏关键信息 | chunk 是否丢标题、overlap 是否太小、rerank 是否需要 |
| 相同问题结果不稳定 | 模型温度、检索索引参数、数据版本 |
| 多租户串数据 | metadata 过滤和权限条件是否强制加入 |

## 十、最小离线示例

下面的示例不用外部向量库，用关键词重叠模拟检索流程，方便理解 RAG 主干。

```python
from dataclasses import dataclass


@dataclass
class SimpleDocument:
    page_content: str
    metadata: dict


docs = [
    SimpleDocument("RAG 会先检索知识库，再让模型根据上下文回答。", {"source": "rag"}),
    SimpleDocument("Milvus 是向量数据库，适合语义搜索和相似度检索。", {"source": "milvus"}),
    SimpleDocument("Text Splitter 会把长文档切成多个文本块。", {"source": "splitter"}),
]


def retrieve(question: str, k: int = 2) -> list[SimpleDocument]:
    query_terms = set(question.lower())
    scored = []
    for doc in docs:
        score = len(query_terms & set(doc.page_content.lower()))
        scored.append((score, doc))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [doc for score, doc in scored[:k] if score > 0]


def build_prompt(question: str, contexts: list[SimpleDocument]) -> str:
    context_text = "\n".join(
        f"- {doc.page_content} 来源：{doc.metadata['source']}"
        for doc in contexts
    )
    return f"请只根据上下文回答。\n\n上下文：\n{context_text}\n\n问题：{question}"


question = "RAG 和 Milvus 分别负责什么？"
contexts = retrieve(question)
print(build_prompt(question, contexts))
```

真实项目把 `retrieve` 替换为 Milvus、Chroma、FAISS 或 Elasticsearch 检索，把最后的 Prompt 交给 LLM 即可。

## 十一、什么样的 RAG 项目更吸引面试官

截图里的问题是“什么样的 RAG 项目才能吸引面试官”。面试官通常不只看“我做了一个知识库问答”，而是看你有没有解决 RAG 的真实工程问题。

一个有含金量的 RAG 项目，最好能讲清楚这几层：

| 层级 | 面试官想听什么 | 可以写进简历的关键词 |
| --- | --- | --- |
| 数据解析 | PDF、图片、PPT、表格、公式如何解析 | OCR、版面分析、表格抽取、多模态解析 |
| 数据质量 | 如何清洗、去重、保留标题层级和来源 | 文档结构化、元数据增强、上下文增强 |
| 切片策略 | 为什么不用简单固定长度切片 | 递归切片、标题切片、语义切片、Parent-Child |
| 检索策略 | 如何兼顾语义和关键词 | Dense + BM25、Hybrid Search、RRF |
| 重排策略 | top_k 很多时如何筛出最相关上下文 | BGE Reranker、Qwen Reranker、Cross-Encoder |
| 生成策略 | 如何减少幻觉和提升可追溯性 | 引用来源、拒答、水位线、结构化回答 |
| 评估体系 | 如何证明效果变好了 | Recall、Precision、F1、MRR、NDCG、端到端准确率 |
| 工程化 | 如何上线、监控、降成本 | 缓存、异步入库、权限过滤、多租户、日志追踪 |

简历里不要只写：

```text
使用 LangChain + Milvus 实现知识库问答。
```

可以改成：

```text
负责企业知识库 RAG 系统，支持 PDF/Markdown/图片文档解析；基于标题递归切片和上下文增强生成可检索 chunk；使用 Milvus 构建 dense+sparse 混合检索，结合 BM25、RRF 和 reranker 提升召回质量；回答返回来源片段，并用 Recall@K、MRR 和人工评测集持续评估。
```

如果是实习或学习项目，也可以写得朴素一点：

```text
完成一个可复现的 RAG Demo：实现文档加载、递归切片、向量化、Milvus/Chroma 检索、Prompt 组装和来源展示；对比固定切片、标题切片、语义切片和 rerank 前后的检索效果。
```

## 十二、传统 RAG 的三大难题与上下文增强

根据智谱 GLM 全模态知识库的“上下文增强技术报告”和 Anthropic 的 Contextual Retrieval 思路，传统 RAG 在复杂知识库里常见三类问题：

### 1. 上下文缺失导致语义漂移

固定长度切片会把段落从原文结构里拿出来。比如“该系统性能提升 30%”如果脱离章节标题，模型不知道“该系统”是什么，也不知道这个指标属于哪个产品或时间范围。

改进方式：

- 切片时保留标题路径，例如 `文档名 > 章节 > 小节`。
- 给每个 chunk 增加上下文摘要卡片。
- 检索时返回 chunk 的父级段落或相邻窗口。

### 2. 关键元信息丢失导致检索失败

用户经常用“文档名、年份、章节、产品型号、人员名称”来提问。如果这些信息没有出现在 chunk 本文里，单纯向量检索可能找不到。

改进方式：

- 元数据字段单独保存：`source`、`title`、`section`、`page`、`date`、`product`。
- 把重要元信息拼入 embedding 文本。
- 检索时结合 metadata filter 和 BM25。

### 3. 单一检索模式能力不足

向量检索擅长语义相似，但对型号、编号、人名、精确短语不稳定；BM25 擅长关键词，但不懂同义词和上下位概念。

更稳的工程路线：

```text
原始问题
-> query rewrite / query expansion
-> dense vector search
-> sparse / BM25 search
-> metadata filter
-> Weighted RRF / RRFRanker 融合
-> reranker 精排
-> score threshold / context compression
-> LLM answer with citations
```

上下文增强的核心做法是：在入库前给每个 chunk 生成一段“这段内容在原文中处于什么位置、主要讲什么、关键实体是什么”的描述，再把“上下文描述 + 原始 chunk”一起参与索引或检索。

## 十三、切片优化：固定切片、递归切片、语义切片

截图中提到“固定长度会割裂语义”，这是 RAG 项目最容易被问到的点。

| 切片方式 | 优点 | 缺点 | 适合场景 |
| --- | --- | --- | --- |
| 固定长度切片 | 简单、稳定、容易实现 | 容易切断句子、标题和表格 | Demo、兜底方案 |
| 递归切片 | 优先按标题/段落/句子切 | 参数需要调 | 通用文档 |
| Markdown 标题切片 | 保留标题层级 | 依赖文档结构规范 | 技术文档、知识库 |
| 语义切片 | 按语义断点切，连贯性更好 | 需要 embedding 或模型，成本高 | 长文、论文、合同 |
| Parent-Child 切片 | 小块检索，大块返回 | 实现稍复杂 | 需要完整上下文的问答 |

工程经验：

- 先结构化，再切片。不要把 PDF 解析出的乱序文本直接切。
- 标题路径要进入 metadata，也可以进入 embedding 文本。
- 表格要保留表头；公式、图片要保留说明或 OCR 结果。
- 检索用小 chunk，生成可返回 parent chunk，兼顾召回和上下文完整性。

## 十四、多模态 RAG

多模态 RAG 解决的是 PDF、扫描件、PPT、图片、表格、图表、音频等非纯文本资料的问答。

截图里提到的方向可以整理成：

```text
PDF / 图片 / PPT
-> OCR / Layout Parser / 多模态模型
-> 文本、图片、表格、公式结构化
-> 文本 embedding + 图像 embedding / 多模态 embedding
-> Milvus 多向量字段或多 collection
-> 混合检索 + rerank
-> 多模态 LLM 生成答案
```

常见模型和工具：

| 类型 | 例子 | 作用 |
| --- | --- | --- |
| OCR / 文档解析 | PaddleOCR、Dolphin、Dots.OCR、DeepSeek-OCR | 从扫描件、图片、PDF 中提取文本和版面 |
| 多模态 embedding | GME-Qwen2-VL、CLIP 系列、ColPali/ColQwen | 把文本、图片或页面转成统一向量空间 |
| 文本 embedding | BGE、Qwen Embedding、OpenAI text-embedding | 文本语义检索 |
| reranker | BGE Reranker、Qwen Reranker、Cohere Rerank | 对候选 chunk 精排 |
| 多模态推理 | Qwen-VL、GLM-4V/GLM-4.5V、GPT-4o/4.1 类视觉模型 | 读取图片或图表并生成答案 |

多模态 RAG 的难点：

- OCR 误识别会污染检索。
- 表格、图片和正文之间的引用关系容易丢。
- 单个页面可能同时包含标题、图、表、脚注，切片要保留布局关系。
- 图像向量和文本向量的分数尺度不同，融合时要归一化或单独 rerank。

## 十五、Reranker 为什么重要

RAG 常用“两阶段检索”：

```text
第一阶段：向量/BM25 快速召回 top 20-100
第二阶段：reranker 对 query-document pair 精排，选 top 3-8 给 LLM
```

Embedding 检索通常是 bi-encoder：问题和文档分别编码，速度快，适合大规模召回。Reranker 通常是 cross-encoder：把问题和候选文档一起输入模型打分，速度慢但相关性判断更强。

什么时候需要 reranker：

- 检索结果“差一点”，top 20 里有答案，但 top 3 不稳定。
- 文档里有大量相似段落。
- 问题包含多个条件，需要精确判断匹配程度。
- 混合检索后需要统一排序。

什么时候 reranker 帮助有限：

- 第一阶段完全没召回正确片段。
- 文档解析和切片质量太差。
- 问题本身需要多跳推理，而不是简单片段相关性。

## 十六、Agentic RAG

Agentic RAG 可以理解为：

```text
RAG + Agent = Agentic RAG
```

传统 RAG 是线性流程：检索一次，生成一次。Agentic RAG 把 Agent 放进 RAG 流程，让它可以决定是否改写问题、是否多次检索、用哪个知识源、是否调用工具、结果是否足够、是否需要追问。

典型流程：

```text
用户问题
-> Agent 判断问题类型
-> 改写 / 拆解子问题
-> 选择检索源：向量库、BM25、图谱、Web、工具 API
-> 多轮检索和证据收集
-> 评估证据是否足够
-> 不足则继续检索或换策略
-> 生成带引用的答案
```

适合 Agentic RAG 的场景：

- 多跳问题，例如“对比 A 公司 2023 和 2024 的研发投入变化，并解释原因”。
- 需要多个知识源，例如内部制度 + 数据库 + 网页。
- 需要工具调用，例如查实时价格、跑 SQL、读文件、画图。
- 需要自我校验，例如回答前检查引用是否支持结论。

不适合过度 Agentic 的场景：

- FAQ、固定客服话术、单文档精确问答。
- 延迟要求极低的在线服务。
- 工具权限很敏感且没有完善审计。

## 十七、RAG 评估指标

截图里提到“评估问得多”，面试里常问怎么证明 RAG 有效果。

| 指标 | 衡量什么 | 常见用法 |
| --- | --- | --- |
| Recall@K | 正确片段是否进入前 K 个结果 | 检索召回 |
| Precision@K | 前 K 个结果里相关片段比例 | 检索纯度 |
| MRR | 第一个正确结果排得多靠前 | 排序质量 |
| NDCG | 多个相关结果的排序质量 | 有分级标注时使用 |
| Faithfulness | 回答是否被上下文支持 | 防幻觉 |
| Answer Correctness | 最终答案是否正确 | 端到端评估 |
| Citation Accuracy | 引用是否真的支持答案 | 可追溯性 |
| Latency / Cost | 延迟和 token 成本 | 工程上线 |

实战建议：

- 自建 50-200 条业务问题集，比只看主观体验可靠。
- 每条问题要标注标准答案、相关文档、相关片段。
- 分开评估“检索是否命中”和“生成是否答对”。
- 改切片、embedding、top_k、rerank、prompt 时都跑同一套评测集。

## 十八、当前资料索引

- [Milvus Full Text Search](https://milvus.io/docs/full-text-search.md)：BM25 Function、`VARCHAR enable_analyzer=True`、`SPARSE_FLOAT_VECTOR`、`SPARSE_INVERTED_INDEX`。
- [Milvus Hybrid Search](https://milvus.io/docs/hybrid_search_with_milvus.md)：dense、sparse、hybrid 三种检索，BGE-M3 可同时产生 dense 和 sparse 向量。
- [Milvus Reranking](https://milvus.io/docs/reranking.md)：`WeightedRanker` 和 `RRFRanker` 用于多路召回融合。
- [智谱上下文增强技术报告](https://docs.bigmodel.cn/cn/guide/tools/knowledge/contextual)：传统 RAG 三大难题、上下文摘要卡片、双索引、Weighted RRF、缓存和评估。
- [Anthropic Contextual Retrieval](https://www.anthropic.com/research/contextual-retrieval)：为 chunk 增加上下文后再做 embedding/BM25，并配合 rerank 降低检索失败率。
- [GME-Qwen2-VL 多模态 Embedding](https://modelscope.cn/models/iic/gme-Qwen2-VL-2B-Instruct)：统一处理文本、图像、图文对等多模态检索输入。
- [BAAI bge-reranker-large](https://huggingface.co/BAAI/bge-reranker-large)：中文和英文 reranker，输入 query-passage pair 输出相关性分数。
- [Qwen3 Embedding 与 Reranker](https://qwenlm.github.io/blog/qwen3-embedding/)：Qwen 官方文本 embedding 和 reranking 模型系列。
- [Agentic RAG Survey](https://arxiv.org/search/cs?query=Agentic+RAG+survey&searchtype=all)：Agentic RAG 把自主 Agent 嵌入 RAG 流程，处理多步检索、工具选择和证据评估。

# Python Milvus 学习笔记

本文档整理 Milvus 在 RAG 项目中的常用知识：本地运行方式、Docker Standalone、PyMilvus 建表、向量字段、BM25 稀疏向量、索引、混合检索和 reranker。Notebook 版示例保存在 `python_milvus_notes.ipynb`，这里侧重复习和工程速查。

安全说明：下面的命令和代码只用于学习说明。涉及删除 collection、清空数据、重建库表的操作，只写作概念解释，不直接执行。

## 一、Milvus 在 RAG 中的位置

Milvus 是向量数据库，负责保存文本 chunk 的向量、原文和元数据，并在用户提问时做相似度检索。

```text
文档 -> Loader -> Splitter -> Embedding -> Milvus
问题 -> Embedding -> Milvus Search -> Top-k Chunks -> LLM
```

Milvus 不负责生成答案。它的职责是：

- 存储稠密向量、稀疏向量、原文和元数据。
- 根据 query 向量做 ANN 近似最近邻检索。
- 结合标量字段过滤，例如租户、来源、时间、分类。
- 通过索引提升检索速度。
- 在 hybrid search 中融合 dense、sparse、全文等多路结果。

## 二、本地运行方式

### 1. Milvus Lite

Milvus Lite 是 `pymilvus` 中的本地嵌入式模式，数据保存在本地 `.db` 文件里，不需要 Docker，适合 notebook、课程演示和小数据量原型。

```bash
pip install -U pymilvus
```

```python
from pymilvus import MilvusClient

client = MilvusClient("./milvus_demo.db")
```

适合：

- 学习 PyMilvus API。
- 本地快速验证 collection、insert、search。
- 小规模 RAG Demo。

不适合：

- 多人共享服务。
- 大规模数据。
- 分布式部署和生产高可用。

### 2. Docker Standalone

Milvus Standalone 是单机服务部署形态。课程截图中提到“所有组件打包在 Docker 镜像中”，适合一台机器上快速运行 Milvus 服务。

推荐资源：

| 操作系统 | 软件 | 备注 |
| --- | --- | --- |
| macOS 10.14+ | Docker Desktop | 建议给 Docker 至少 2 vCPU、8 GB 内存 |
| Linux | Docker Engine 19.03+ | 适合服务器和课程环境 |
| Windows | Docker Desktop + WSL2 | 注意虚拟化和端口映射 |

常见安装脚本方式：

```bash
curl -sfL https://raw.githubusercontent.com/milvus-io/milvus/master/scripts/standalone_embed.sh -o standalone_embed.sh

# 启动 Milvus
bash standalone_embed.sh start

# 停止 Milvus
bash standalone_embed.sh stop
```

服务启动后，常见连接地址：

```text
Milvus gRPC: http://127.0.0.1:19530
Milvus WebUI: http://127.0.0.1:9091/webui/
```

Python 连接：

```python
from pymilvus import MilvusClient

client = MilvusClient(uri="http://127.0.0.1:19530")
```

## 三、Schema、字段和数据类型

Milvus 的 collection 类似关系型数据库中的表。schema 决定每条记录包含哪些字段。

RAG 常见字段：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `id` | `INT64` 或 `VARCHAR` | 主键，可自增或使用业务 ID |
| `text` | `VARCHAR` | chunk 原文 |
| `dense` | `FLOAT_VECTOR` | 稠密向量 |
| `sparse` | `SPARSE_FLOAT_VECTOR` | BM25 或稀疏向量 |
| `source` | `VARCHAR` | 来源文件 |
| `page` | `INT64` | 页码 |
| `title` | `VARCHAR` | 标题或章节 |
| `tenant_id` | `VARCHAR` | 多租户隔离 |

创建 schema 示例：

```python
from pymilvus import DataType, Function, FunctionType, MilvusClient

client = MilvusClient(uri="http://127.0.0.1:19530")

schema = client.create_schema(auto_id=True)
schema.add_field(field_name="id", datatype=DataType.INT64, is_primary=True)
schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=2000, enable_analyzer=True)
schema.add_field(field_name="dense", datatype=DataType.FLOAT_VECTOR, dim=1024)
schema.add_field(field_name="sparse", datatype=DataType.SPARSE_FLOAT_VECTOR)
schema.add_field(field_name="source", datatype=DataType.VARCHAR, max_length=500)
```

`enable_analyzer=True` 用于让文本字段参与 analyzer 分词，这对 BM25 Function 和全文检索很重要。

## 四、BM25 Function 与稀疏向量

BM25 是经典关键词检索算法。它根据词频、逆文档频率和文档长度归一化计算相关性。Milvus 可以用 BM25 Function 从 `text` 字段生成稀疏向量，并把结果写入 `sparse` 字段。

```python
bm25_function = Function(
    name="text_bm25_emb",
    input_field_names=["text"],
    output_field_names=["sparse"],
    function_type=FunctionType.BM25,
)

schema.add_function(bm25_function)
```

数据写入时，只需要写入原始文本字段，Milvus 会根据 Function 生成稀疏向量：

```python
rows = [
    {
        "text": "Milvus 支持 dense+sparse 混合检索。",
        "dense": dense_vector,
        "source": "milvus_notes.md",
    }
]
```

BM25 适合：

- 产品型号、订单号、法规条款号等精确词。
- 人名、机构名、专有名词。
- 用户问题很短，语义向量不稳定的场景。

BM25 不擅长：

- 同义表达。
- 抽象语义。
- 需要上下位概念理解的问题。

## 五、索引类型

索引是在向量字段上建立的附加结构，用于加快搜索速度。索引会消耗构建时间、内存或磁盘空间，也可能影响召回率。

### 1. 稠密向量索引

| 索引 | 说明 | 适合场景 |
| --- | --- | --- |
| `FLAT` | 暴力搜索，召回最高，速度慢 | 小数据、评测基线 |
| `IVF_FLAT` | 聚类倒排，速度较快 | 中等规模 |
| `IVF_SQ8` | IVF + 量化，内存更低 | 内存敏感场景 |
| `IVF_PQ` | 乘积量化，压缩更强 | 大规模、可接受精度损失 |
| `HNSW` | 图搜索，查询快、精度高 | 高召回、低延迟，内存较高 |
| `DISKANN` | 面向磁盘的大规模索引 | 数据量很大、内存有限 |
| `AUTOINDEX` | Milvus 自动选择策略 | 不想手动调参 |

HNSW 示例：

```python
index_params = client.prepare_index_params()

index_params.add_index(
    field_name="dense",
    index_name="dense_vector_index",
    index_type="HNSW",
    metric_type="IP",
    params={"M": 16, "efConstruction": 64},
)
```

HNSW 参数：

| 参数 | 说明 |
| --- | --- |
| `M` | 图中每个节点的邻居数，越大召回越高，内存越高 |
| `efConstruction` | 建图时搜索宽度，越大索引质量越好，构建越慢 |
| `ef` | 查询时搜索宽度，越大召回越高，延迟越高 |

### 2. 稀疏向量索引

BM25 稀疏向量通常使用 `SPARSE_INVERTED_INDEX`。

```python
index_params.add_index(
    field_name="sparse",
    index_name="sparse_inverted_index",
    index_type="SPARSE_INVERTED_INDEX",
    metric_type="BM25",
    params={
        "inverted_index_algo": "DAAT_MAXSCORE",
        "bm25_k1": 1.6,
        "bm25_b": 0.75,
    },
)
```

参数含义：

| 参数 | 说明 |
| --- | --- |
| `inverted_index_algo` | 倒排索引查询算法 |
| `bm25_k1` | 控制词频饱和度，常见范围约 1.2-2.0 |
| `bm25_b` | 控制文档长度归一化，常用 0.75 |

## 六、相似度指标

常见向量距离或相似度：

| 指标 | 说明 | 注意点 |
| --- | --- | --- |
| `L2` | 欧氏距离，越小越近 | 适合未归一化向量或明确距离语义 |
| `IP` | 内积，越大越相似 | 向量归一化后近似 cosine |
| `COSINE` | 余弦相似度 | 关注方向，文本语义检索常用 |
| `BM25` | 稀疏关键词相关性 | 用于 sparse 字段 |

如果 embedding 模型开启 `normalize_embeddings=True`，常用 `IP` 或 `COSINE`。如果前后模型或归一化策略改变，历史向量通常需要重新生成。

## 七、Hybrid Search 与 Rerank

混合检索的核心是：同时做 dense 语义检索和 sparse/BM25 关键词检索，再把结果融合排序。

```text
query
-> dense embedding search
-> sparse BM25 search
-> WeightedRanker / RRFRanker
-> top-k candidates
-> reranker 精排
-> LLM 生成答案
```

常见融合方式：

| 方式 | 说明 | 适合场景 |
| --- | --- | --- |
| WeightedRanker | 给 dense、sparse 分数设置权重后融合 | 有明确权重偏好 |
| RRFRanker | 根据排名做 Reciprocal Rank Fusion | 多路分数尺度不一致 |

经验：

- dense 负责语义召回，sparse 负责关键词召回。
- sparse 可以显著改善编号、英文缩写、产品名、人名的召回。
- fusion 后候选数可以取 20-100，再用 reranker 精排。
- reranker 通常比 embedding 更懂 query-document pair 的细粒度相关性，但速度更慢。

## 八、查询、搜索和过滤

Milvus 中 `search` 和 `query` 要区分：

| API | 是否需要向量 | 用途 |
| --- | --- | --- |
| `search` | 需要 | 向量相似度检索 |
| `query` | 不需要 | 按字段条件查询记录 |

向量搜索常见形式：

```python
results = client.search(
    collection_name="rag_docs",
    data=[query_vector],
    anns_field="dense",
    filter='source == "product_faq.md"',
    limit=5,
    output_fields=["text", "source", "page", "title"],
)
```

标量查询常见形式：

```python
rows = client.query(
    collection_name="rag_docs",
    filter='source == "product_faq.md" and page >= 1',
    output_fields=["text", "source", "page"],
)
```

过滤条件适合：

- 多租户隔离：`tenant_id == "tenant-a"`。
- 权限控制：只查用户有权限的 `department` 或 `doc_id`。
- 时间范围：只查最新版本文档。
- 文件范围：只在某个产品手册内检索。

## 九、RAG 工程建议

### 1. Collection 设计

小项目可以一个 collection 存所有文档，通过 metadata 区分来源。企业项目更常见的做法是：

- 按业务域拆 collection，例如 `product_docs`、`policy_docs`。
- 或按租户拆 collection，简化权限隔离。
- 保留稳定的业务 ID，支持增量更新。
- 保存 `doc_id`、`chunk_id`、`source`、`title_path`、`page`、`version`。

### 2. 入库流程

```text
读取文件
-> 解析和清洗
-> 标题/语义切片
-> 生成 dense embedding
-> 写入 text、dense、metadata
-> Milvus 自动生成 sparse BM25
-> 建索引和加载 collection
```

入库前后要抽样检查：

- 文本是否乱码。
- 页码和标题是否正确。
- chunk 是否过短或过长。
- dense 维度是否和 schema 一致。
- 检索 top-k 是否能命中人工问题集。

### 3. 排查清单

| 现象 | 可能原因 | 处理 |
| --- | --- | --- |
| 插入失败 | 字段缺失、类型不匹配、向量维度不一致 | 检查 schema 和每条 row |
| 搜索为空 | collection 未加载、过滤条件过严、向量字段错 | 先去掉 filter，用小样本搜 |
| 结果不相关 | chunk 质量差、embedding 不适合、top_k 太小 | 抽样看 chunk，调整切片和模型 |
| 编号搜不到 | 只用了 dense 检索 | 增加 BM25 / sparse / 全文检索 |
| 延迟高 | 无索引、索引参数过大、候选过多 | 建索引，调小 `ef`、`nprobe`、top_k |
| 多租户串数据 | filter 没强制加租户条件 | 在检索服务层统一注入权限过滤 |

## 十、学习路线

建议按这个顺序练：

1. Milvus Lite：本地 `.db` 文件创建 collection、insert、search。
2. Docker Standalone：连接 `127.0.0.1:19530`，用 WebUI 查看 collection。
3. Schema：理解主键、`VARCHAR`、`FLOAT_VECTOR`、`SPARSE_FLOAT_VECTOR`。
4. 索引：对比 `FLAT`、`HNSW`、`IVF_FLAT` 的速度和召回。
5. BM25 Function：从 `text` 生成 sparse 字段。
6. Hybrid Search：dense + sparse 多路召回。
7. Reranker：对候选片段精排。
8. 接入 LangChain：把 Milvus 包装成 VectorStore 或 Retriever。

## 十一、参考链接

- Milvus Quickstart: <https://milvus.io/docs/quickstart.md>
- Milvus Standalone Docker: <https://milvus.io/docs/install_standalone-docker-compose.md>
- Milvus Full Text Search: <https://milvus.io/docs/full-text-search.md>
- Milvus Hybrid Search: <https://milvus.io/docs/hybrid_search_with_milvus.md>
- Milvus Reranking: <https://milvus.io/docs/reranking.md>
- LangChain Milvus Integration: <https://docs.langchain.com/oss/python/integrations/vectorstores/milvus>

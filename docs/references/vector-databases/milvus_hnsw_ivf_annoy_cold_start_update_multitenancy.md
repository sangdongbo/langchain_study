# Milvus 索引与工程问题详解：HNSW、IVF、Annoy、冷启动、增量更新、多租户

> 适用场景：RAG 知识库、语义搜索、推荐召回、相似图片/文本检索。  
> 说明：下面的代码是工程写法参考，不在本仓库中执行任何 Milvus 写入、删除、建索引或迁移操作。

## 1. 先理解 Milvus 的数据与索引机制

Milvus 的向量索引不是“整库一个大索引”这么简单。它会把 collection 中的数据切成多个 segment：

- 新写入的数据先进入 **growing segment**，主要承担实时写入和近实时查询。
- flush 后变成 **sealed segment**，sealed segment 是只读的，适合构建索引。
- 每个 sealed segment 可以独立构建索引，因此新数据通常不需要把全量历史索引推倒重建。
- 删除和更新不是直接修改老向量文件，而是通过主键、时间戳、bitset/软删除、compaction 等机制让旧数据在查询时不可见，并在后台整理。

这决定了 Milvus 的几个工程特性：

- 新文档可以先插入并被检索，后续再异步形成高性能索引。
- 增量写入不会要求重建整个 collection 的索引，但新增 sealed segment 仍然需要单独建索引。
- 更新向量本质上更接近“写入新版本 + 屏蔽旧版本”，而不是原地改索引节点。

参考资料：

- Milvus Data Processing: https://milvus.io/docs/data_processing.md
- Milvus Index Explained: https://milvus.io/docs/index-explained.md
- Milvus Upsert Entities: https://milvus.io/docs/upsert-entities.md
- Milvus Delete Entities: https://milvus.io/docs/delete-entities.md

## 2. HNSW、IVF、Annoy 的核心区别

### 2.1 HNSW：图索引，低延迟、高召回、内存更贵

HNSW 是 Hierarchical Navigable Small World 的缩写。它会把向量组织成多层近邻图：

- 上层图节点少，负责快速跳到大致相近区域。
- 底层图节点多，负责精细搜索。
- 查询时从上层入口点开始贪心搜索，再逐层下探。

适合：

- 高维向量，例如文本 embedding、图片 embedding。
- 需要低延迟和较高召回的在线检索。
- topK 较小或中等，例如 top 5、top 20、top 100。
- 数据规模较大，但内存资源比较充足。

不适合：

- 内存极度紧张的场景。
- 写入非常频繁且要求每条数据立刻进入完整图索引的场景。
- topK 非常大时，HNSW 的优势可能不如 IVF 明显。

常用参数：

| 参数 | 阶段 | 含义 | 调大后的影响 |
| --- | --- | --- | --- |
| `M` | 建索引 | 每个节点保留的邻居数 | 召回提升，内存和构建时间增加 |
| `efConstruction` | 建索引 | 构图时搜索候选集合大小 | 召回提升，构建更慢 |
| `ef` | 查询 | 查询时维护的候选集合大小 | 召回提升，延迟增加 |

PyMilvus 示例：

```python
from pymilvus import MilvusClient

client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")

index_params = MilvusClient.prepare_index_params()
index_params.add_index(
    field_name="embedding",
    index_type="HNSW",
    metric_type="COSINE",
    params={
        "M": 16,
        "efConstruction": 200,
    },
)

# 参考代码：创建索引。请在真实环境确认 collection、字段、资源后再执行。
# client.create_index(collection_name="doc_chunks", index_params=index_params)

search_params = {"params": {"ef": 64}}
```

经验值：

- RAG 知识库优先从 `M=16`、`efConstruction=100~200`、`ef=32~128` 开始压测。
- 如果召回不够，先增加 `ef`；如果整体质量仍不够，再提高 `M` 或 `efConstruction`。
- 如果内存压力大，考虑 HNSW_SQ、HNSW_PQ、IVF_SQ8、IVF_PQ、DiskANN 等方案。

官方文档：  
https://milvus.io/docs/hnsw.md

### 2.2 IVF：聚类倒排，吞吐好、内存更省、需要调参

IVF 是 Inverted File 的缩写。它先用聚类算法把向量空间分成多个桶，每个桶有一个中心点。查询时先找离 query 最近的若干中心点，再只扫描这些桶里的向量。

常见 IVF 变体：

- `IVF_FLAT`：桶内保留原始向量，不压缩，召回较好，内存占用高于压缩型。
- `IVF_SQ8`：使用 8-bit scalar quantization 压缩，内存更省，召回有损。
- `IVF_PQ`：使用 product quantization，压缩率更高，适合更大数据量或内存受限场景。

适合：

- 数据量大，要求较高吞吐。
- topK 较大，例如一次要召回几千条候选。
- 可接受通过调参在“速度、召回、内存”之间折中。
- 有较强标量过滤时，IVF 在某些场景下比图索引更稳。

不适合：

- 极致低延迟、极高召回，并且内存充足的场景，这时 HNSW 往往更自然。
- 数据分布变化很快、聚类中心明显失效的场景，需要重新评估索引。

常用参数：

| 参数 | 阶段 | 含义 | 调大后的影响 |
| --- | --- | --- | --- |
| `nlist` | 建索引 | 聚类桶数量 | 桶更细，构建更慢，查询可更精确 |
| `nprobe` | 查询 | 查询时扫描多少个桶 | 召回提升，延迟增加 |

PyMilvus 示例：

```python
from pymilvus import MilvusClient

client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")

index_params = MilvusClient.prepare_index_params()
index_params.add_index(
    field_name="embedding",
    index_type="IVF_FLAT",
    metric_type="COSINE",
    params={"nlist": 1024},
)

# 参考代码：创建索引。请在真实环境确认 collection、字段、资源后再执行。
# client.create_index(collection_name="doc_chunks", index_params=index_params)

search_params = {"params": {"nprobe": 16}}
```

经验值：

- `nlist` 可以从 `sqrt(N)` 或几百到几千开始压测，不要机械套公式。
- `nprobe` 可以从 `8、16、32、64` 做召回/延迟曲线。
- 数据量越大、topK 越大，IVF 的性价比越容易体现。
- 如果内存不足，再考虑 `IVF_SQ8` 或 `IVF_PQ`。

官方文档：  
https://milvus.io/docs/ivf-flat.md  
https://milvus.io/docs/ivf-sq8.md

### 2.3 Annoy：树索引，历史上常见，但当前 Milvus 生产选型要谨慎

Annoy 全称 Approximate Nearest Neighbors Oh Yeah，最初由 Spotify 开源。它的核心思路是构建多棵随机投影树，把向量空间不断切分；查询时沿多棵树找到候选，再做距离比较。

Annoy 的特点：

- 构建和查询逻辑相对简单。
- 索引文件可以 mmap，适合某些只读或读多写少场景。
- 对动态更新不友好，通常更偏离线构建。
- 高维、强实时更新、大规模高召回场景下，通常不是首选。

在 Milvus 语境里要特别注意：

- Milvus 底层向量执行引擎 Knowhere 的文档提到集成过 Faiss、Hnswlib、Annoy。
- 但当前 Milvus v3.0 文档的 FLOAT_VECTOR 可选索引列表中没有把 `ANNOY` 列为用户常规创建的向量索引类型。
- 因此在新的 Milvus 项目里，通常应优先选择 `HNSW`、`IVF_*`、`AUTOINDEX`、`DISKANN` 或 GPU 索引，而不是把 Annoy 当成首选生产方案。

Annoy 更适合作为理解 ANN 的一个算法参照：

| 维度 | HNSW | IVF | Annoy |
| --- | --- | --- | --- |
| 结构 | 多层近邻图 | 聚类倒排桶 | 多棵随机投影树 |
| 查询延迟 | 很低 | 取决于 `nprobe` | 较低但看数据分布 |
| 召回 | 通常较高 | 依赖聚类和 `nprobe` | 依赖树数量和搜索节点 |
| 内存 | 较高 | 中等，可压缩 | 可 mmap，但更新弱 |
| 增量更新 | 数据库层可增量写，索引按 segment 处理 | 数据库层可增量写，索引按 segment 处理 | 算法本身更偏静态 |
| 当前 Milvus 推荐度 | 高 | 高 | 新项目谨慎 |

参考资料：  
https://milvus.io/docs/knowhere.md  
https://milvus.io/docs/index-explained.md

## 3. 冷启动问题：新文档的 Embedding 怎么快速索引？

### 3.1 冷启动的本质

冷启动有两类：

1. **新 collection 冷启动**：刚创建知识库，没有历史索引，需要导入第一批文档并让它可查。
2. **新文档冷启动**：线上已有知识库，新上传文档要尽快被搜索到。

目标不是“每条新向量立刻进入完美索引”，而是：

- 尽快可查。
- 查询结果不要跨租户、跨权限。
- 后台逐步形成高性能索引。
- 不因为少量新增数据频繁触发昂贵建索引。

### 3.2 推荐写入链路

```text
文档上传
  -> 文本抽取/OCR
  -> chunk 切分
  -> embedding 批量生成
  -> 写入 Milvus growing segment
  -> 立即可通过强/有界一致性查询新数据
  -> 后台 flush / sealed segment
  -> segment 级索引构建
  -> 查询自动合并 growing + sealed 结果
```

工程建议：

- 使用稳定的业务主键，例如 `tenant_id + doc_id + chunk_id + embedding_version`。
- 插入时同时写入 `tenant_id`、`doc_id`、`chunk_id`、`source`、`acl`、`created_at`、`embedding_model` 等标量字段。
- collection 提前创建好索引参数，不要等线上流量来了再临时设计。
- 批量写入 embedding，例如每批 100~1000 条，避免单条 RPC 写入造成吞吐浪费。
- 对新文档查询使用合适一致性级别，避免用户刚上传却搜不到。
- 对 RAG 可加一个应用层状态：`index_status = pending | searchable | indexed | failed`。

参考插入代码：

```python
from pymilvus import MilvusClient

client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")

rows = [
    {
        "id": "tenant_a:doc_001:chunk_0001:v1",
        "tenant_id": "tenant_a",
        "doc_id": "doc_001",
        "chunk_id": 1,
        "text": "这里是 chunk 原文",
        "embedding": [0.01, 0.02, 0.03],  # 示例，真实维度要与 schema 一致
        "embedding_model": "text-embedding-model-v1",
        "acl": ["role:sales", "user:10086"],
        "created_at": 1783670400,
    }
]

# 参考代码：写入新文档向量。
# client.insert(collection_name="doc_chunks", data=rows)
```

### 3.3 快速可查与高性能索引的折中

对于新写入数据，不建议为了“马上索引”而频繁强制 flush 和手动建索引：

- 少量数据频繁 flush 会产生很多小 segment，后续查询和 compaction 成本变高。
- 频繁建索引会增加 CPU、内存、IO 压力，影响在线查询。
- Milvus 的架构本来就允许 growing segment 和 sealed segment 一起参与查询。

更稳的做法：

- 写入后让数据先以 growing segment 参与查询。
- 后台按批次或按数据量 flush。
- sealed segment 形成后，由后台构建 segment 级索引。
- 对实时性特别强的业务，应用层可以短期把“最近上传文档”单独加权或补查。

### 3.4 大批量冷启动导入

如果是首次导入百万级、千万级向量：

- 先离线生成 embedding 文件。
- 校验 schema、维度、主键、租户字段、权限字段。
- 分批导入 Milvus。
- 导入完成后再 load / 建索引 / 验证召回。
- 用抽样 query 检查召回、延迟、过滤条件、权限隔离。

索引选择：

- 中小规模、高召回、内存足：`HNSW`。
- 大规模、高吞吐、topK 较大：`IVF_FLAT` 或 `IVF_SQ8`。
- 内存紧张：`IVF_PQ`、`IVF_SQ8`、mmap、DiskANN。
- 不想一开始就调复杂参数：可以先用 `AUTOINDEX` 做基线，再针对压测结果改成显式索引。

## 4. 增量更新：怎么在不重建索引的情况下更新向量？

### 4.1 Milvus 中“更新”的正确理解

向量数据库里的更新通常不是原地修改某个索引节点。更常见的是：

```text
旧实体存在
  -> upsert / delete + insert
  -> 新实体写入
  -> 旧实体通过主键或删除标记不可见
  -> 查询时通过时间戳、bitset、主键语义过滤旧版本
  -> 后台 compaction 清理旧数据
  -> 新 sealed segment 单独建索引
```

所以“不重建索引”更准确地说是：

- 不重建整个 collection 的历史索引。
- 新增或更新的数据进入新的 segment。
- 只对新形成的 sealed segment 建索引。
- 旧数据通过删除标记、compaction 和版本字段逐步清理。

### 4.2 推荐使用 upsert

Milvus 的 `upsert` 会根据主键判断是插入新实体还是更新旧实体：

- 主键不存在：插入。
- 主键存在：更新。
- override mode：更接近“插入新实体 + 删除旧实体”。
- merge mode：Milvus 2.6.2+ 支持 `partial_update=True`，可以只传需要更新的字段。

参考代码：

```python
from pymilvus import MilvusClient

client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")

row = {
    "id": "tenant_a:doc_001:chunk_0001:v2",
    "tenant_id": "tenant_a",
    "doc_id": "doc_001",
    "chunk_id": 1,
    "text": "更新后的 chunk 原文",
    "embedding": [0.04, 0.05, 0.06],
    "embedding_model": "text-embedding-model-v2",
    "is_active": True,
}

# 参考代码：根据主键插入或更新。
# client.upsert(collection_name="doc_chunks", data=[row])
```

### 4.3 更推荐的 RAG 更新模式：版本化写入

在 RAG 知识库中，直接覆盖同一个主键不一定是最稳的做法。更推荐版本化：

```text
doc_id = doc_001
chunk_id = 1
embedding_version = v1 / v2 / v3
is_active = true / false
```

主键示例：

```text
tenant_a:doc_001:chunk_0001:v1
tenant_a:doc_001:chunk_0001:v2
```

更新流程：

1. 为新文档版本生成新的 chunk 和 embedding。
2. 插入新版本，`is_active = true`。
3. 将旧版本标记为不可用，或按主键删除旧版本。
4. 查询时固定加过滤条件：`tenant_id == "tenant_a" && is_active == true`。
5. 后台定期清理旧版本，降低存储和查询负担。

优点：

- 支持回滚。
- 支持灰度切换 embedding 模型。
- 支持审计和排查“为什么答案变了”。
- 避免用户查询期间看到半更新状态。

参考删除旧版本代码：

```python
# 参考代码：删除指定旧版本。真实环境应严格带 tenant_id 条件，避免误删。
# client.delete(
#     collection_name="doc_chunks",
#     filter='tenant_id == "tenant_a" && doc_id == "doc_001" && embedding_version == "v1"'
# )
```

### 4.4 什么时候需要重建索引？

一般增量新增和普通更新不需要重建整个 collection 索引。但下面情况要考虑重建或新建 collection：

- embedding 模型整体升级，所有向量都要重新生成。
- 向量维度变化，例如 768 维变成 1024 维。Milvus vector 字段维度固定，通常需要新 collection。
- 索引类型或关键参数需要整体调整，例如 IVF 改 HNSW，或 `nlist` 严重不合理。
- 数据分布发生明显变化，原 IVF 聚类效果变差。
- 历史删除/更新太多，compaction 后仍需重新评估性能。

推荐迁移方式：

```text
旧 collection: doc_chunks_v1
新 collection: doc_chunks_v2
  -> 后台全量重嵌入
  -> 双写或回放增量
  -> 抽样验证召回和权限过滤
  -> 切读流量
  -> 保留旧 collection 一段时间
```

## 5. 多租户隔离：共享集群里怎么做租户级别的数据隔离？

Milvus 支持多种租户隔离方式，隔离强度和资源成本不同。

### 5.1 方案一：共享 collection + `tenant_id` 字段过滤

所有租户共用一个 collection，每条数据带 `tenant_id`。

查询时必须加过滤条件：

```python
# 参考代码：租户过滤必须由服务端统一拼接，不要信任前端传入。
# client.search(
#     collection_name="doc_chunks",
#     data=[query_embedding],
#     anns_field="embedding",
#     filter='tenant_id == "tenant_a" && is_active == true',
#     limit=10,
#     search_params={"metric_type": "COSINE", "params": {"ef": 64}},
#     output_fields=["doc_id", "chunk_id", "text", "source"],
# )
```

优点：

- 实现简单。
- collection 数量少，运维轻。
- 适合租户很多、单租户数据不大、隔离要求中等的 SaaS 场景。

缺点：

- 隔离主要靠应用层过滤和 Milvus scalar filter，属于逻辑隔离。
- 如果服务端漏加 `tenant_id` 过滤，会出现严重数据越权。
- 高过滤比例下，索引和过滤组合需要压测，否则延迟可能抖动。

安全要求：

- `tenant_id` 过滤必须在后端中间层强制拼接。
- 不允许客户端直接传完整 filter 表达式。
- 所有 query、search、delete、upsert 都要带租户上下文。
- 日志要记录 tenant、collection、filter、topK、request_id。

### 5.2 方案二：Partition Key 多租户

把 `tenant_id` 设置成 partition key。Milvus 会根据 partition key 的 hash 把数据路由到内部 partition；查询时带 `tenant_id` 过滤，Milvus 可以缩小搜索范围。

适合：

- 租户较多，但不想为每个租户手动建 partition。
- 希望兼顾共享 collection 的简单运维和更好的搜索性能。
- SaaS RAG 知识库按租户隔离，但 schema 基本一致。

建 schema 示例：

```python
from pymilvus import MilvusClient, DataType

client = MilvusClient(uri="http://localhost:19530", token="root:Milvus")

schema = client.create_schema()
schema.add_field(field_name="id", datatype=DataType.VARCHAR, is_primary=True, max_length=256)
schema.add_field(field_name="embedding", datatype=DataType.FLOAT_VECTOR, dim=1536)
schema.add_field(
    field_name="tenant_id",
    datatype=DataType.VARCHAR,
    max_length=128,
    is_partition_key=True,
)
schema.add_field(field_name="doc_id", datatype=DataType.VARCHAR, max_length=128)
schema.add_field(field_name="text", datatype=DataType.VARCHAR, max_length=8192)

# 参考代码：创建 collection。
# client.create_collection(
#     collection_name="doc_chunks",
#     schema=schema,
#     properties={"partitionkey.isolation": True},  # HNSW 场景可考虑
# )
```

查询要求：

```python
# 必须包含 partition key 条件。
tenant_filter = 'tenant_id == "tenant_a" && is_active == true'
```

注意点：

- partition key 字段不能为空。
- 开启 Partition Key Isolation 后，搜索 filter 中应只包含一个明确的 partition key 值。
- 当前 Partition Key Isolation 主要适用于 HNSW 索引场景。
- 仍然要在业务层强制注入租户过滤，不能只依赖约定。

官方文档：  
https://milvus.io/docs/use-partition-key.md

### 5.3 方案三：一个 partition 一个租户

手动为每个租户创建一个 partition。

优点：

- 比纯 `tenant_id` 过滤更明确。
- 可以按 partition 加载、释放、删除或迁移。
- 中等数量租户时比较直观。

缺点：

- Milvus 单 collection 的手动 partition 数量有限。
- 租户很多时管理复杂。
- 租户数量增长快的 SaaS 不适合长期靠这个方案。

适合：

- 租户数量可控。
- 每个租户数据量较大。
- 需要按租户做加载、卸载、资源管理。

### 5.4 方案四：一个 collection 一个租户

每个租户一个 collection。

优点：

- 数据隔离更强。
- 每个租户可以有不同 schema、索引参数、生命周期。
- 删除租户数据更清晰。

缺点：

- collection 数量多会增加调度、元数据、加载和运维成本。
- 不适合租户非常多的小客户场景。

适合：

- 租户数量不多，但单租户数据量大。
- 不同租户 schema 或索引策略不同。
- 企业级客户要求更强隔离。

### 5.5 方案五：一个 database 一个租户

Milvus 支持在同一集群里创建多个 database。可以给每个租户一个 database，让租户拥有自己的 collections 和 partitions。

优点：

- 逻辑隔离更强。
- 更适合部门级、项目级、企业客户级隔离。
- 对 schema 差异更友好。

缺点：

- database 数量也有上限和管理成本。
- 空闲租户会浪费部分资源。
- 仍然共享底层集群资源，不等于物理隔离。

适合：

- 企业内部多部门。
- 中大型客户专属知识库。
- 需要更清晰的管理边界。

官方多租户文档：  
https://milvus.io/docs/v2.4.x/multi_tenancy.md

### 5.6 多租户方案对比

| 方案 | 隔离强度 | 运维成本 | 租户数量 | 适合场景 |
| --- | --- | --- | --- | --- |
| 共享 collection + `tenant_id` filter | 低到中 | 低 | 很多 | 小租户、多租户 SaaS |
| Partition Key | 中 | 低到中 | 很多 | schema 一致的 SaaS RAG |
| 每租户一个 partition | 中 | 中 | 有限 | 租户数量可控 |
| 每租户一个 collection | 高 | 高 | 中等 | 大客户、强隔离 |
| 每租户一个 database | 高 | 高 | 较少 | 部门/项目/企业级边界 |
| 每租户独立集群 | 最高 | 最高 | 较少 | 合规、金融、政企强隔离 |

### 5.7 推荐的共享集群 SaaS RAG 方案

如果是常见 SaaS 知识库，推荐：

```text
Milvus cluster
  -> database: app_prod
  -> collection: doc_chunks
  -> partition key: tenant_id
  -> scalar fields: tenant_id, doc_id, chunk_id, acl, is_active, embedding_version
  -> vector index: HNSW 或 IVF_FLAT/IVF_SQ8
  -> service layer: 强制注入 tenant_id + ACL filter
```

查询过滤：

```text
tenant_id == current_tenant
&& is_active == true
&& acl in current_user_permissions
```

删除或更新：

```text
tenant_id == current_tenant
&& doc_id == target_doc
```

关键原则：

- 租户隔离必须由服务端统一控制。
- 所有 Milvus 操作都要携带租户上下文。
- 主键最好带租户前缀，避免不同租户的 doc_id/chunk_id 冲突。
- 不要把用户输入直接拼成 Milvus filter，需要白名单化字段和操作符。
- 对高价值租户可以升级到独立 collection、database 或独立集群。

## 6. 索引选型建议

### 6.1 RAG 知识库默认建议

优先选择：

- 数据量中等、追求高召回低延迟：`HNSW`
- 数据量很大、topK 较大、吞吐优先：`IVF_FLAT`
- 内存紧张：`IVF_SQ8`、`IVF_PQ`、`HNSW_SQ`
- 不确定：先用 `AUTOINDEX` 建基线，再压测显式索引

### 6.2 压测指标

不要只看单次查询，要看曲线：

- p50 / p95 / p99 延迟
- QPS
- recall@5 / recall@10 / recall@50
- 内存占用
- index build 时间
- 新增文档从写入到可查的时间
- 新增文档从写入到 indexed 的时间
- 带 `tenant_id` 和 ACL filter 后的延迟
- compaction 和索引构建对在线查询的影响

### 6.3 一个实用起点

小到中型 RAG：

```text
index_type = HNSW
metric_type = COSINE
M = 16
efConstruction = 200
search ef = 64
```

大规模 RAG：

```text
index_type = IVF_FLAT
metric_type = COSINE
nlist = 1024 或 4096 起步压测
search nprobe = 16 / 32 / 64 做曲线
```

内存紧张：

```text
index_type = IVF_SQ8 或 IVF_PQ
metric_type = COSINE
用召回曲线确认压缩损失是否可接受
```

## 7. 常见坑

### 7.1 只更新文本，不更新 embedding

如果 chunk 文本变了，embedding 必须重新生成。否则检索仍按旧语义召回。

### 7.2 主键设计不稳定

不建议用随机 UUID 作为唯一识别来源。更推荐：

```text
tenant_id:doc_id:chunk_id:embedding_version
```

这样方便 upsert、删除旧版本、排查问题。

### 7.3 忘记租户过滤

这是多租户 RAG 最大风险。必须在服务端强制加：

```text
tenant_id == current_tenant
```

不要让前端决定 filter。

### 7.4 频繁强制 flush

为了让新数据“马上索引”而高频 flush，可能造成大量小 segment，反而让查询和后台整理变慢。

### 7.5 只看无过滤压测

真实 RAG 一般都有：

- `tenant_id`
- `doc_id`
- `is_active`
- `acl`
- `created_at`
- `source`

压测必须带真实 filter，否则结果会过于乐观。

## 8. 一句话总结

- **HNSW**：图索引，低延迟、高召回，内存成本更高，是很多 RAG 在线检索的首选。
- **IVF**：聚类倒排，适合大规模、高吞吐、topK 较大的场景，需要认真调 `nlist` 和 `nprobe`。
- **Annoy**：树索引，适合理解 ANN 或部分静态索引场景；当前 Milvus 新项目不要优先把它当生产索引选项。
- **冷启动**：新 embedding 先批量 insert/upsert 进入 growing segment，保证快速可查；后台再 flush、sealed、segment 级建索引。
- **增量更新**：用 upsert 或版本化 insert + 删除/禁用旧版本，不重建全量历史索引。
- **多租户隔离**：共享集群优先考虑 `tenant_id` + partition key + 服务端强制过滤；大客户再升级到 collection、database 或独立集群隔离。

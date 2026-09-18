# 综合智能体教学项目设计

## 背景

当前仓库已经有独立的 RAG 示例和 ERP 工具调用示例。新项目需要参考图片中的智能体项目结构，做成一个单独的教学型智能体项目，用来展示工具、RAG、向量库、模型工厂、中间件、日志和 Streamlit 页面如何协同工作。

新项目放在 `agent_demo/` 下，尽量保持代码独立。它可以复用根目录 `.env` 和项目依赖，但不直接依赖 `rag_demo` 或 `streamlit_v2` 的业务代码。

## 目标

- 新建一个可运行的综合智能体教学项目。
- 展示清晰的模块分层：页面、Agent 编排、工具、中间件、RAG 服务、向量库、模型工厂、工具类。
- 支持上传本地文档、写入独立 ChromaDB、RAG 问答和文档总结。
- 支持教学用 mock 工具调用，例如用户 ID、当前位置、当前月份、天气和外部数据生成。
- 在页面中展示运行日志，方便讲解智能体执行过程。
- 保持实现简单直接，适合学习和课堂演示。

## 非目标

- 不改造现有 `rag_demo` 或 `streamlit_v2`。
- 不接入真实企业数据库、真实天气接口或真实外部业务系统。
- 不执行数据库迁移、数据库测试或任何数据库读写操作。
- 不做前端打包或构建。

## 项目结构

```text
agent_demo/
  app.py
  README.md
  config/
    settings.py
  data/
    sample_docs/
  prompts/
    agent_system.md
    rag_summary.md
  model/
    factory.py
  rag/
    rag_service.py
    vector_store.py
  tools/
    agent_tools.py
  utils/
    file_handler.py
    logger_handler.py
    path_tools.py
    prompt_loader.py
  middleware.py
  react_agent.py
```

## 数据流

```text
Streamlit app.py
  -> ReactAgent
    -> middleware records prompt/tool/model events
    -> tools/agent_tools.py handles mock tools and RAG tool entry points
    -> rag/RagSummarizeService retrieves and summarizes documents
      -> rag/VectorStoreService loads documents and creates retriever
      -> model/factory.py creates chat model and embedding model
```

上传文档流程：

```text
app.py upload
  -> utils/file_handler.py decodes files
  -> VectorStoreService.load_documents()
  -> split documents
  -> skip duplicate file hashes
  -> persist chunks into agent_demo/chroma_db/
  -> logger records indexing result
```

用户提问流程：

```text
app.py question
  -> ReactAgent.execute_stream()
  -> route intent by simple rules
  -> call mock tool, RAG summarize, or RAG answer
  -> middleware records each step
  -> app.py renders answer, sources, and logs
```

## 模块设计

### `app.py`

Streamlit 教学工作台。左侧提供文档上传、写入向量库、检索数量和日志清理。主区域提供问题输入、智能体回答和检索片段展示。页面只负责交互，不放业务编排细节。

### `react_agent.py`

Agent 编排层。第一版使用清晰可控的规则路由，而不是直接引入复杂 LangGraph 流程：

- 包含“总结、概括、摘要”时走 RAG 总结。
- 包含“天气”时调用天气 mock 工具。
- 包含“位置、在哪”时调用位置 mock 工具。
- 包含“用户、user_id”时调用用户 ID 工具。
- 包含“月份、当前月”时调用当前月份工具。
- 其余问题走 RAG 问答。

保留 `execute_stream()` 作为统一入口。第一版可以返回分段结果列表或生成器，页面逐步渲染；后续可以替换为真实模型流式输出。

### `middleware.py`

提供教学用中间件函数：

- `monitor_tool()`：记录工具调用名称、参数和结果摘要。
- `log_before_model()`：记录调用模型前的 prompt 类型和上下文长度。
- `report_prompt_switch()`：记录当前选择了哪个 prompt。

中间件只做日志和可观测性，不改变业务结果。

### `tools/agent_tools.py`

提供智能体可调用工具：

- `rag_summarize(query)`：基于知识库检索并总结。
- `get_weather(location)`：返回 mock 天气。
- `get_user_location()`：返回 mock 用户位置。
- `get_user_id()`：返回 mock 用户 ID。
- `get_current_month()`：返回当前月份。
- `generate_external_data(topic)`：返回 mock 外部数据。

工具返回结构化 dict，方便页面和日志统一展示。

### `rag/vector_store.py`

负责向量库底层能力：

- 文档转 Document。
- 文档切分。
- 文件哈希去重。
- ChromaDB 持久化到 `agent_demo/chroma_db/`。
- 创建 retriever。

默认使用本地 hash embedding，方便没有 embedding API 的环境也能演示。配置 `RAG_EMBEDDING_PROVIDER=openai` 时可切换到 OpenAI-compatible embedding。

### `rag/rag_service.py`

负责 RAG 业务能力：

- `retrieve_docs(question)`：检索相关片段。
- `answer(question)`：基于检索上下文回答。
- `rag_summarize(query)`：基于检索上下文做总结。
- `_load_prompt_text()`：加载 prompt 文件。

该模块依赖 `VectorStoreService` 和 `model.factory`，但不直接接触 Streamlit。

### `model/factory.py`

统一创建模型：

- 优先使用 `DEEPSEEK_API_KEY` 和 `langchain_deepseek.ChatDeepSeek`。
- 没有 DeepSeek 时回退到 OpenAI-compatible chat model。
- embedding 默认使用本地 hash embedding。
- 读取配置时集中在 `config/settings.py`。

### `utils/`

工具类保持小而明确：

- `file_handler.py`：上传文件解码、文本清洗。
- `logger_handler.py`：日志数据结构和格式化。
- `path_tools.py`：项目路径、向量库路径、样例文档路径。
- `prompt_loader.py`：读取 prompt 文件并给出友好错误。

## 页面设计

页面采用教学工作台布局：

- 左侧：文档上传、写入向量库、检索数量、日志控制。
- 主区域顶部：项目标题和能力标签。
- 主区域中部：问题输入和执行按钮。
- 主区域下部：智能体回答、调用过程、检索片段。

页面文字以中文为主，按钮和提示保持简洁。

## 错误处理

- 上传空文件时跳过并提示。
- 重复文件根据哈希跳过，不重复入库。
- 没有可检索文档时，回答说明需要先上传并写入资料。
- 缺少模型 API key 时，在页面展示清晰错误。
- Chroma 依赖缺失时给出安装提示。
- 工具执行异常会被中间件记录，并返回友好的错误消息。

## 验证

遵守仓库 AGENTS 规则，不运行数据库相关测试，不执行迁移或数据库命令。

实现后优先运行：

```powershell
python -m compileall agent_demo
```

如需人工页面验证，运行：

```powershell
streamlit run agent_demo/app.py
```

不运行 `npm run build`，也不进行任何前端打包。

## 实施边界

第一版聚焦教学闭环：上传文档、入库、提问、工具路由、RAG 回答、总结、日志展示。后续可以再扩展 LangGraph 真正 ReAct 循环、真实天气 API、更多业务工具和更完整的流式输出。

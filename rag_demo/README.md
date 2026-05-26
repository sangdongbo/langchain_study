# 本地 RAG 搜索助手

一个独立的 Streamlit + LangChain LCEL + ChromaDB 示例。

## 功能

- 左侧上传多个 `.txt`、`.md`、`.markdown` 文件。
- 点击“写入 ChromaDB”后，文本会被切块并保存到 `rag_demo/chroma_db/`。
- 每个文件会计算 MD5 指纹；同样内容再次上传时会跳过，避免重复入库。
- 右侧输入问题后，会先从 ChromaDB 检索相似片段，再调用 DeepSeek 生成回答。
- 页面和终端都会打印上传、解析、入库、检索、模型调用日志。

## 环境变量

复用项目根目录 `.env`。推荐直接使用 DeepSeek 专用配置：

```env
DEEPSEEK_API_KEY=your_deepseek_api_key_here
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TEMPERATURE=0.7
```

如果没有 `DEEPSEEK_API_KEY`，代码才会回退到 `OPENAI_API_KEY`、`OPENAI_BASE_URL`、`OPENAI_MODEL`。

向量嵌入默认使用本地 hash embedding，方便课堂 demo 在只有 DeepSeek chat key 时也能入库和检索。
如果你希望使用 OpenAI-compatible embedding 服务，可以改成：

```env
RAG_EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

此时请确保 `OPENAI_BASE_URL` 和 `OPENAI_API_KEY` 指向支持 embedding 的服务。

## 启动

```powershell
streamlit run rag_demo/app.py
```

## 代码结构

- `app.py`：Streamlit 页面。
- `rag_chain.py`：文档转换、切分、Chroma 持久化、检索、LCEL 问答链。
- `chroma_db/`：本地向量库目录，已加入 `.gitignore`。

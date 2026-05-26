# 综合智能体学习项目

这是一个独立的智能体学习项目，用于演示 Agent 项目常见模块如何协同工作：

- `app.py`：Streamlit 页面。
- `react_agent.py`：规则路由版 Agent 编排。
- `tools/agent_tools.py`：学习用 LangChain tools。
- `middleware.py`：工具、prompt、模型调用日志。
- `rag/rag_service.py`：RAG 问答和总结服务。
- `rag/vector_store.py`：文档切分、去重、ChromaDB 接入。
- `model/factory.py`：聊天模型和 embedding 创建。
- `utils/`：路径、文件、日志、prompt 加载工具。

## 日志

页面侧边栏会显示最近的运行日志，同时日志也会按天写入本地文件：

```text
agent_demo/logs/YYYY-MM-DD.log
```

`agent_demo/logs/` 已加入 `.gitignore`，运行日志不会提交到仓库。

## 启动

```powershell
streamlit run agent_demo/app.py
```

## 环境变量

优先使用 DeepSeek：

```env
DEEPSEEK_API_KEY=your_key
DEEPSEEK_MODEL=deepseek-chat
DEEPSEEK_TEMPERATURE=0.2
```

没有 DeepSeek 时回退到 OpenAI-compatible 配置：

```env
OPENAI_API_KEY=your_key
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4.1-mini
```

embedding 默认使用本地 hash embedding，方便本地学习演示。如果要切换为 OpenAI-compatible embedding：

```env
RAG_EMBEDDING_PROVIDER=openai
OPENAI_EMBEDDING_MODEL=text-embedding-3-small
```

## 验证

本项目不需要数据库迁移，也不执行数据库测试。推荐先运行纯逻辑测试：

```powershell
python -m pytest tests/test_agent_demo_utils.py tests/test_agent_demo_agent.py -q
```

再做语法检查：

```powershell
python -m compileall agent_demo
```

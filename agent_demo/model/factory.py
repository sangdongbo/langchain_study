from __future__ import annotations

"""模型工厂。

项目里所有“创建模型”的逻辑集中在这里：
- 页面和 RAG service 不关心用 DeepSeek 还是 OpenAI-compatible。
- 环境变量读取集中在 settings.py。
- embedding 默认使用本地 hash embedding，方便无额外 key 的本地学习演示。
"""

from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from agent_demo.config.settings import AgentDemoSettings, load_settings
from agent_demo.rag.vector_store import LocalHashEmbeddings


def create_chat_model(settings: AgentDemoSettings | None = None) -> ChatDeepSeek | ChatOpenAI:
    """创建聊天模型。

    优先使用 DeepSeek；如果没有 DEEPSEEK_API_KEY，就回退到 OpenAI-compatible。
    传入 settings 参数主要是为了测试和后续扩展，正常运行时直接读环境变量。
    """

    current = settings or load_settings()
    if not current.chat_api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY 或 DEEPSEEK_API_KEY，无法调用聊天模型。")

    if current.chat_provider == "deepseek":
        # ChatDeepSeek 使用 DeepSeek 官方 LangChain 封装。
        return ChatDeepSeek(
            model=current.chat_model,
            api_key=current.chat_api_key,
            temperature=current.temperature,
            timeout=30,
            max_retries=1,
        )

    # OpenAI-compatible 可以连接 OpenAI，也可以连接其它兼容 Chat Completions 的服务。
    return ChatOpenAI(
        api_key=current.chat_api_key,
        base_url=current.openai_base_url,
        model=current.chat_model,
        temperature=current.temperature,
    )


def create_embeddings(settings: AgentDemoSettings | None = None):
    """创建 embedding 模型。

    默认返回 LocalHashEmbeddings，不需要网络和 API key。
    如果设置 RAG_EMBEDDING_PROVIDER=openai，则使用 OpenAIEmbeddings。
    """

    current = settings or load_settings()
    if current.embedding_provider == "local":
        return LocalHashEmbeddings()

    if not current.chat_api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY，无法创建 OpenAI-compatible embedding。")

    return OpenAIEmbeddings(
        api_key=current.chat_api_key,
        base_url=current.openai_base_url,
        model=current.embedding_model,
    )

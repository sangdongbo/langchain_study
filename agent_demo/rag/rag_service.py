from __future__ import annotations

"""RAG 业务服务。

`vector_store.py` 只负责“找资料”，这个文件负责“拿资料组织 prompt 并调用模型”。
也就是说，RagSummarizeService 是 RAG 的业务层：
- retrieve_docs：只检索。
- answer：检索后问答。
- rag_summarize：检索后总结。
"""

from operator import itemgetter
from typing import Protocol, Sequence

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.runnables import RunnableLambda, RunnableParallel, RunnablePassthrough

from agent_demo.model.factory import create_chat_model
from agent_demo.rag.vector_store import VectorStoreService, format_documents
from agent_demo.utils.prompt_loader import load_prompt


class RetrieverService(Protocol):
    """检索服务协议。

    用 Protocol 的原因是方便测试：单元测试可以传入 FakeVectorStoreService，
    只要它有 retrieve(query, k) 方法即可，不需要真的打开 ChromaDB。
    """

    def retrieve(self, query: str, k: int = 4) -> list[Document]:
        ...


class RagSummarizeService:
    """RAG 问答和总结服务。"""

    def __init__(self, vector_store: RetrieverService | None = None, model=None) -> None:
        # 默认使用真实向量库和真实模型；测试时可以注入 fake。
        self.vector_store = vector_store or VectorStoreService()
        self.model = model or create_chat_model()

    def retrieve_docs(self, question: str, k: int = 4) -> list[Document]:
        """只做检索，不调用模型。"""

        return self.vector_store.retrieve(question, k=k)

    def answer(self, question: str, k: int = 4) -> str:
        """基于知识库片段回答问题。"""

        return self.build_answer_chain(k=k).invoke(question)

    def rag_summarize(self, query: str, k: int = 4) -> str:
        """基于知识库片段做主题总结。"""

        return self.build_summary_chain(k=k).invoke(query)

    def build_answer_chain(self, k: int = 4):
        """构建完整 LCEL RAG 问答链。

        链路是：
        用户问题 -> 检索 docs -> 格式化 context -> prompt -> model -> 字符串

        检索步骤也在 LCEL 里，因此这不只是“检索后手动拼 prompt”，而是完整链式编排。
        """

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", load_prompt("agent_system.md")),
                ("human", "问题：{question}\n\n参考资料：\n{context}\n\n请基于参考资料回答。"),
            ]
        )
        return self._retrieval_inputs(k) | prompt | self.model | StrOutputParser()

    def build_summary_chain(self, k: int = 4):
        """构建完整 LCEL RAG 总结链。"""

        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", load_prompt("rag_summary.md")),
                ("human", "总结主题：{query}\n\n参考资料：\n{context}"),
            ]
        )
        return (
            self._retrieval_inputs(k)
            | {
                "query": itemgetter("question"),
                "context": itemgetter("context"),
            }
            | prompt
            | self.model
            | StrOutputParser()
        )

    def _retrieval_inputs(self, k: int):
        """把输入问题扩展成 prompt 需要的字段。

        RunnableParallel 会并行构造：
        - question：原始问题，原样传下去。
        - docs：根据问题检索到的 Document 列表。

        后面的 RunnableLambda 再把 docs 格式化成 context。
        """

        return (
            RunnableParallel(
                question=RunnablePassthrough(),
                docs=RunnableLambda(lambda question: self.retrieve_docs(question, k=k)),
            )
            | {
                "question": itemgetter("question"),
                "context": itemgetter("docs") | RunnableLambda(format_documents),
            }
        )

    @staticmethod
    def sources_for_display(documents: Sequence[Document]) -> list[dict[str, str]]:
        """把 Document 转成页面展示结构。"""

        return [
            {
                "source": str(doc.metadata.get("source", "未知来源")),
                "content": doc.page_content.strip(),
            }
            for doc in documents
        ]

from __future__ import annotations

"""向量库底层能力。

这个文件负责 RAG 的“资料入库”和“资料检索”基础设施：
1. 把上传文本转成 LangChain Document。
2. 把长文档切成适合检索的小 chunk。
3. 用 file_md5 跳过重复文件。
4. 用 ChromaDB 保存和检索向量。

注意：这里不负责调用大模型回答问题。回答和总结属于 `rag_service.py`。
"""

import re
from collections import Counter
from dataclasses import dataclass
from hashlib import blake2b, md5
from math import sqrt
from pathlib import Path
from typing import Iterable, Sequence

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

from agent_demo.utils.file_handler import UploadedText
from agent_demo.utils.path_tools import chroma_dir

try:
    from langchain_chroma import Chroma
except ImportError:  # pragma: no cover
    Chroma = None


DEFAULT_COLLECTION_NAME = "agent_demo"


@dataclass(frozen=True)
class IndexingResult:
    """一次写入知识库后的结果摘要。

    added_chunks：本次真正新增的文本块数量。
    skipped_files：因为内容重复而跳过的文件名。
    indexed_files：本次新增文件的文件名和 MD5，方便排查入库记录。
    """

    added_chunks: int
    skipped_files: list[str]
    indexed_files: list[tuple[str, str]]

    def summary(self) -> str:
        """生成适合页面展示的一句话摘要。"""

        message = f"写入 {self.added_chunks} 个文本块"
        if self.skipped_files:
            message += "，跳过重复文件：" + "、".join(self.skipped_files)
        return message


class LocalHashEmbeddings(Embeddings):
    """本地学习用 embedding。

    正式 RAG 一般会用 OpenAI、bge、text2vec 等语义向量模型。
    这个类用“词哈希”生成固定长度向量，不需要任何 API key，适合本地离线学习演示。

    它能演示 ChromaDB 的写入/检索流程，但语义效果不等同真实 embedding 模型。
    """

    def __init__(self, dimensions: int = 512) -> None:
        # dimensions 是向量维度。维度越大，hash 冲突越少，但存储和计算也略增。
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """Chroma 写入多段文档时调用。返回“每段文本一个向量”。"""

        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """Chroma 查询时调用。把用户问题也转成同一空间里的向量。"""

        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        """把文本转成归一化向量。"""

        # 先准备一个全 0 向量，后续把不同 token 映射到不同维度。
        vector = [0.0] * self.dimensions

        # Counter 记录 token 频次。某个词出现越多，它对向量的影响越大。
        counts = Counter(self._tokenize(text))
        for token, count in counts.items():
            # blake2b 是稳定 hash：同一个 token 每次都会落到同一个维度。
            digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions

            # 用 hash 的另一个字节决定正负号，减少所有 token 都正向累加造成的偏置。
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * float(count)

        # 归一化后，长文本和短文本不会只因为长度不同而距离差异过大。
        norm = sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """轻量分词：英文按单词，中文按单字。

        这不是高质量中文分词，只是为了让学习 demo 在无额外依赖时可运行。
        """

        normalized = text.lower()
        words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)
        return words or list(normalized.strip())


def file_md5(text: str) -> str:
    """计算文本 MD5，用于文件去重。

    这里 MD5 不是安全用途，只是为了判断“同样内容是否已经入库”。
    """

    return md5(text.encode("utf-8")).hexdigest()


def documents_from_uploads(files: Iterable[UploadedText]) -> list[Document]:
    """把页面上传后的纯文本对象转成 LangChain Document。

    Document 由两部分组成：
    - page_content：真正参与 embedding 和检索的文本。
    - metadata：来源文件、后缀、编码、MD5 等辅助信息。
    """

    documents: list[Document] = []
    for file in files:
        text = file.text.strip()
        if not text:
            continue
        suffix = Path(file.name).suffix.lower()
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source": file.name,
                    "suffix": suffix,
                    "encoding": file.encoding,
                    "file_md5": file_md5(text),
                },
            )
        )
    return documents


def split_documents(
    documents: Sequence[Document],
    chunk_size: int = 700,
    chunk_overlap: int = 120,
) -> list[Document]:
    """把长文档切成多个 chunk。

    RAG 一般不会把整篇长文直接塞给模型：
    - 太长会浪费上下文窗口。
    - 检索粒度太粗，命中的内容可能不够精确。

    chunk_overlap 让相邻片段保留重叠区域，减少一句话被切断后检索不到的问题。
    """

    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )
    return splitter.split_documents(list(documents))


def chunk_ids(documents: Sequence[Document]) -> list[str]:
    """为每个 chunk 生成稳定 ID。

    稳定 ID 的好处是：同一个文件同一个 chunk 再次处理时 ID 可预测，
    后续排查、覆盖或删除记录会更容易。
    """

    ids: list[str] = []
    for index, doc in enumerate(documents):
        digest = doc.metadata.get("file_md5") or file_md5(doc.page_content)
        doc.metadata["file_md5"] = digest
        doc.metadata["chunk_index"] = index
        ids.append(f"{digest}-chunk-{index}")
    return ids


def format_documents(documents: Sequence[Document]) -> str:
    """把检索到的 Document 拼成 prompt 里的“参考资料”。"""

    if not documents:
        return "未检索到相关资料。"

    formatted: list[str] = []
    for index, doc in enumerate(documents, start=1):
        source = doc.metadata.get("source", "未知来源")
        formatted.append(f"[{index}] 来源：{source}\n{doc.page_content.strip()}")
    return "\n\n".join(formatted)


class VectorStoreService:
    """ChromaDB 访问封装。

    页面和 RAG service 不直接操作 Chroma，而是通过这个类完成入库和检索。
    这样可以把“向量库细节”限制在一个文件里，后续替换 Milvus、FAISS 等也更容易。
    """

    def __init__(
        self,
        persist_directory: Path | str | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        embeddings: Embeddings | None = None,
    ) -> None:
        # 默认把向量库放在 agent_demo/chroma_db/，与现有 rag_demo 数据隔离。
        self.persist_directory = Path(persist_directory) if persist_directory else chroma_dir()
        self.collection_name = collection_name
        self.embeddings = embeddings or LocalHashEmbeddings()

    def get_store(self):
        """创建或打开 Chroma collection。"""

        if Chroma is None:
            raise RuntimeError("缺少 langchain-chroma 依赖，请先安装 langchain-chroma。")
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        return Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=str(self.persist_directory),
        )

    def load_documents(self, documents: Sequence[Document]) -> IndexingResult:
        """把文档写入向量库，并按 file_md5 跳过重复内容。"""

        if not documents:
            return IndexingResult(added_chunks=0, skipped_files=[], indexed_files=[])

        vector_store = self.get_store()
        new_documents: list[Document] = []
        skipped_files: list[str] = []
        indexed_files: list[tuple[str, str]] = []

        for document in documents:
            digest = document.metadata.get("file_md5") or file_md5(document.page_content)
            source = document.metadata.get("source", "未知文件")

            # Chroma 支持按 metadata 查询。只要同一个 file_md5 已经存在，
            # 就认为这个文件内容已经入过库，本次跳过。
            existing = vector_store.get(where={"file_md5": digest}, limit=1)
            if existing.get("ids"):
                skipped_files.append(source)
                continue
            new_documents.append(document)
            indexed_files.append((source, digest))

        if not new_documents:
            return IndexingResult(added_chunks=0, skipped_files=skipped_files, indexed_files=indexed_files)

        chunks = split_documents(new_documents)
        vector_store.add_documents(chunks, ids=chunk_ids(chunks))
        return IndexingResult(
            added_chunks=len(chunks),
            skipped_files=skipped_files,
            indexed_files=indexed_files,
        )

    def retrieve(self, query: str, k: int = 4) -> list[Document]:
        """根据用户问题检索最相似的 k 个文本片段。"""

        return self.get_store().similarity_search(query, k=k)

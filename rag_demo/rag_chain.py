"""RAG 示例的核心逻辑。

RAG 可以简单理解为：
1. 把本地文档切成小块。
2. 把每个小块转成向量并保存到 ChromaDB。
3. 用户提问时，先从向量库找最相关的小块。
4. 把这些小块作为“参考资料”交给大模型生成回答。

这个文件只负责数据处理、向量库和 LangChain 链路，不负责 Streamlit 页面。
如果你是 Python 新手，可以按这个顺序阅读：
1. UploadedText / IndexingResult / LogEntry：先看数据结构。
2. documents_from_uploads / split_documents：再看文档如何准备。
3. get_embeddings / get_vector_store / add_documents_to_store：再看如何入库。
4. retrieve_documents / build_rag_chain / answer_with_context：最后看如何检索和回答。
"""

from __future__ import annotations

import os
import re
from collections import Counter
from dataclasses import dataclass
from datetime import datetime
from hashlib import blake2b, md5
from math import sqrt
from operator import itemgetter
from pathlib import Path
from typing import Iterable, Sequence

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter

try:
    from langchain_chroma import Chroma
except ImportError:  # pragma: no cover - protects older local installs.
    Chroma = None


DEFAULT_COLLECTION_NAME = "local_rag_demo"
DEFAULT_CHROMA_DIR = Path(__file__).resolve().parent / "chroma_db"

SYSTEM_PROMPT = """你是一个严谨的本地知识库问答助手。
请只依据给定的参考资料回答问题；如果资料里没有答案，直接说明没有找到相关依据。
回答要简洁、中文优先，并在必要时引用来源文件名。"""


@dataclass(frozen=True)
class UploadedText:
    """页面上传后的纯文本文件。

    name 是原文件名，text 是解码后的文本内容。
    这个类是 Streamlit 上传文件和 LangChain Document 之间的过渡对象。
    """

    name: str
    text: str


@dataclass(frozen=True)
class IndexingResult:
    """一次入库操作的结果摘要。

    added_chunks：本次真正新增到 ChromaDB 的文本块数量。
    skipped_files：因为 MD5 已存在而跳过的文件名。
    indexed_files：本次新增入库的文件名和对应 MD5。
    """

    added_chunks: int
    skipped_files: list[str]
    indexed_files: list[tuple[str, str]]

    def summary(self) -> str:
        """生成适合页面日志展示的中文摘要。"""

        # 先写最核心的结果：本次新增了多少个 chunk。
        message = f"写入 {self.added_chunks} 个文本块"

        # 如果有重复文件，再把跳过列表拼到同一句提示里。
        if self.skipped_files:
            message += "，跳过重复文件：" + "、".join(self.skipped_files)
        return message


@dataclass(frozen=True)
class LogEntry:
    """页面和终端共用的一条运行日志。"""

    stage: str
    message: str
    timestamp: str

    def render(self) -> str:
        """把日志对象变成一行适合显示/打印的文本。"""

        return f"[{self.timestamp}] {self.stage}：{self.message}"


class LocalHashEmbeddings(Embeddings):
    """本地演示用的简易向量模型。

    正式项目一般会使用 OpenAI、bge、text2vec 等 embedding 模型。
    这里为了课堂 demo 能离线入库，使用“词哈希”生成固定长度向量。
    它适合演示 ChromaDB 流程，不适合追求高质量语义检索。
    """

    def __init__(self, dimensions: int = 512) -> None:
        # dimensions 是向量长度。长度越大，冲突越少，但存储也越大。
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        """LangChain 向量库写入文档时会调用这个方法。"""

        # ChromaDB 会一次传入多个文本，所以这里返回“向量列表”。
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        """用户查询时会调用这个方法，把问题也转成向量。"""

        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        """把文本转成一个归一化向量。"""

        # 第 1 步：把原始文本切成 token。
        # 例如英文按单词，中文示例里按单字。
        tokens = self._tokenize(text)

        # 第 2 步：先创建一个全 0 向量。
        # 后面会根据 token 把不同位置加上权重。
        vector = [0.0] * self.dimensions

        # 第 3 步：统计每个 token 出现了几次。
        # 出现次数越多，对向量的影响越大。
        counts = Counter(tokens)
        for token, count in counts.items():
            # blake2b 让同一个 token 永远落到同一个向量位置。
            digest = blake2b(token.encode("utf-8"), digest_size=8).digest()

            # 第 4 步：用 hash 值决定这个 token 写入向量的哪个位置。
            index = int.from_bytes(digest[:4], "big") % self.dimensions

            # 第 5 步：用 hash 的另一个字节决定加正数还是负数。
            # 这样能稍微降低不同 token 撞到同一位置时的偏差。
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * float(count)

        # 第 6 步：归一化向量。
        # 归一化后，长文本和短文本更容易比较方向相似度，而不是只比长度。
        norm = sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        """非常轻量的分词：英文按单词，中文按单字。"""

        # 统一转小写，让 Apple 和 apple 被当作同一个 token。
        normalized = text.lower()

        # 正则含义：
        # - [a-z0-9_]+：连续英文/数字/下划线作为一个词。
        # - [\u4e00-\u9fff]：每个中文字符作为一个词。
        words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)

        # 如果正则没有提取到任何 token，就退回按字符切分，避免返回空向量。
        return words or list(normalized.strip())


def make_log(stage: str, message: str) -> LogEntry:
    """创建一条带当前时间的日志。"""

    # stage 是阶段名，例如“上传”“解析”“入库”。
    # message 是这个阶段的具体说明。
    return LogEntry(
        stage=stage,
        message=message,
        timestamp=datetime.now().strftime("%H:%M:%S"),
    )


def print_log(entry: LogEntry) -> None:
    """打印日志到终端，方便调试 Streamlit 页面行为。"""

    print(entry.render(), flush=True)


def file_md5(text: str) -> str:
    """计算文件内容的 MD5 指纹。

    这里 MD5 只用于去重和追踪文件版本，不用于安全加密。
    """

    # encode("utf-8") 是因为 md5 只能处理 bytes，不能直接处理 str。
    # hexdigest() 返回 32 位十六进制字符串，适合存 metadata。
    return md5(text.encode("utf-8")).hexdigest()


def documents_from_uploads(files: Iterable[UploadedText]) -> list[Document]:
    """把上传文件转成 LangChain Document。

    Document 包含 page_content 和 metadata 两部分：
    - page_content 是实际用于检索的文本。
    - metadata 保存来源文件名、后缀、MD5 等辅助信息。
    """

    documents: list[Document] = []
    for file in files:
        # 第 1 步：去掉文件头尾空白。
        # 如果文件只有空格或换行，就视为无效文件。
        text = file.text.strip()
        if not text:
            continue

        # 第 2 步：记录文件后缀，例如 .txt / .md。
        # 后续如果想按文件类型筛选，这个 metadata 会有用。
        suffix = Path(file.name).suffix.lower()

        # 第 3 步：创建 LangChain Document。
        # page_content 会进入向量库，metadata 不参与语义向量，但会跟着结果返回。
        documents.append(
            Document(
                page_content=text,
                metadata={
                    "source": file.name,
                    "suffix": suffix,
                    # 第 4 步：保存 MD5，用于判断重复上传和追踪文件版本。
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
    """把长文档切成适合入库的小块。

    chunk_overlap 是相邻文本块的重叠字数，可以减少一句话被切断后检索不到的问题。
    """

    # RecursiveCharacterTextSplitter 会按 separators 的顺序尝试切分：
    # 先按段落，再按换行，再按标点，最后实在不行按字符切。
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )

    # split_documents 会保留每个 Document 的 metadata，
    # 所以切出来的 chunk 仍然知道自己来自哪个文件。
    return splitter.split_documents(list(documents))


def chunk_ids(documents: Sequence[Document]) -> list[str]:
    """为每个 chunk 生成稳定 ID。

    稳定 ID 的好处：同一个文件同一个 chunk 再次入库时 ID 可预测，
    后续做删除、覆盖、排查重复数据会更容易。
    """

    ids: list[str] = []
    for index, doc in enumerate(documents):
        # 第 1 步：优先读取前面 documents_from_uploads 写入的 file_md5。
        digest = doc.metadata.get("file_md5")

        # 第 2 步：如果某个 Document 没有 file_md5，就用 chunk 内容临时计算一个。
        # 这是兜底逻辑，避免外部直接传 Document 进来时报错。
        if not digest:
            digest = file_md5(doc.page_content)
            doc.metadata["file_md5"] = digest

        # 第 3 步：把 chunk 序号也写入 metadata，方便调试检索结果。
        doc.metadata["chunk_index"] = index

        # 第 4 步：生成 ChromaDB 记录 ID。
        # 例：abc123...-chunk-0
        ids.append(f"{digest}-chunk-{index}")
    return ids


def format_documents(documents: Sequence[Document]) -> str:
    """把检索结果拼成 prompt 里的参考资料文本。"""

    # 没有检索结果时，也返回一段明确文本，让模型知道没有上下文。
    if not documents:
        return "未检索到相关资料。"

    formatted: list[str] = []
    for index, doc in enumerate(documents, start=1):
        # source 是用户最终能看到的来源文件名。
        source = doc.metadata.get("source", "未知来源")
        content = doc.page_content.strip()

        # 给每段资料编号，模型回答时更容易引用“来源：xxx”。
        formatted.append(f"[{index}] 来源：{source}\n{content}")

    # 用空行分隔每个 chunk，prompt 可读性更好。
    return "\n\n".join(formatted)


def get_embeddings() -> Embeddings:
    """创建向量模型。

    默认走 LocalHashEmbeddings，方便没有 embedding API 时也能演示。
    设置 RAG_EMBEDDING_PROVIDER=openai 后，才会使用 OpenAIEmbeddings。
    """

    # 第 1 步：读取向量模型提供方。
    # 默认 local，课堂测试不用申请额外 embedding API。
    provider = os.getenv("RAG_EMBEDDING_PROVIDER", "local").lower()
    if provider == "local":
        return LocalHashEmbeddings()

    # 第 2 步：如果配置为 openai，就读取 OpenAI-compatible embedding 配置。
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL")
    model = os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small")

    if not api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY，无法创建 OpenAI 向量嵌入。")

    # 第 3 步：返回 LangChain 标准 Embeddings 对象。
    # ChromaDB 只关心这个对象有没有 embed_documents / embed_query 方法。
    return OpenAIEmbeddings(
        api_key=api_key,
        base_url=base_url,
        model=model,
    )


def get_vector_store(
    persist_directory: Path | str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> Chroma:
    """创建或打开本地 Chroma 向量库。"""

    # Chroma 是可选依赖。这里提前报友好错误，而不是让后面 AttributeError。
    if Chroma is None:
        raise RuntimeError("缺少 langchain-chroma 依赖，请先安装 langchain-chroma。")

    # persist_directory 是本地持久化目录。
    # 目录存在就打开旧库，不存在就新建目录。
    persist_path = Path(persist_directory)
    persist_path.mkdir(parents=True, exist_ok=True)

    # collection_name 类似数据库里的表名。
    # embedding_function 告诉 Chroma 如何把文本/问题变成向量。
    return Chroma(
        collection_name=collection_name,
        embedding_function=get_embeddings(),
        persist_directory=str(persist_path),
    )


def add_documents_to_store(
    documents: Sequence[Document],
    persist_directory: Path | str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> IndexingResult:
    """把文档写入 ChromaDB，并用 MD5 跳过重复文件。"""

    # 第 1 步：没有有效文档时直接返回空结果。
    # 这样页面层不需要额外判断 None。
    if not documents:
        return IndexingResult(added_chunks=0, skipped_files=[], indexed_files=[])

    # 第 2 步：创建/打开 ChromaDB。
    # 这一步不会清空旧数据，只会连接到指定 collection。
    vector_store = get_vector_store(persist_directory, collection_name)

    # new_documents：真正需要新增入库的文档。
    # skipped_files：已经入过库、需要跳过的文件名。
    # indexed_files：本次新增的文件名和 MD5，用于日志或后续展示。
    new_documents: list[Document] = []
    skipped_files: list[str] = []
    indexed_files: list[tuple[str, str]] = []

    # 第 3 步：逐个文件按 MD5 查重。
    for document in documents:
        digest = document.metadata.get("file_md5") or file_md5(document.page_content)
        source = document.metadata.get("source", "未知文件")
        # Chroma 的 metadata 查询可以判断这个文件内容是否已经入过库。
        existing = vector_store.get(where={"file_md5": digest}, limit=1)
        if existing.get("ids"):
            # 只要查到任意一条相同 file_md5 的记录，就认为这个文件已入库。
            skipped_files.append(source)
            continue
        new_documents.append(document)
        indexed_files.append((source, digest))

    # 第 4 步：如果全部文件都是重复的，就不再切块、不再写库。
    if not new_documents:
        return IndexingResult(
            added_chunks=0,
            skipped_files=skipped_files,
            indexed_files=indexed_files,
        )

    # 第 5 步：把新增文档切成 chunk。
    # 原始文件可能很长，直接整篇入库会影响检索粒度。
    chunks = split_documents(new_documents)

    # 第 6 步：给每个 chunk 生成稳定 ID，并把 chunk_index 写入 metadata。
    ids = chunk_ids(chunks)

    # add_documents 的 ids 参数让每个向量记录有可追踪的唯一 ID。
    # Chroma 会在这里调用 embedding_function，把 chunk 文本转成向量。
    vector_store.add_documents(chunks, ids=ids)

    # 第 7 步：返回结构化结果，页面据此显示“写入/跳过”信息。
    return IndexingResult(
        added_chunks=len(chunks),
        skipped_files=skipped_files,
        indexed_files=indexed_files,
    )


def retrieve_documents(
    question: str,
    k: int = 4,
    persist_directory: Path | str = DEFAULT_CHROMA_DIR,
    collection_name: str = DEFAULT_COLLECTION_NAME,
) -> list[Document]:
    """根据用户问题从向量库里检索最相似的 k 个文本块。"""

    # 第 1 步：打开和入库时相同的 Chroma collection。
    vector_store = get_vector_store(persist_directory, collection_name)

    # 第 2 步：similarity_search 内部会：
    # - 把 question 转成查询向量。
    # - 和库里文本块向量做相似度比较。
    # - 返回最相似的 k 个 Document。
    return vector_store.similarity_search(question, k=k)


def get_chat_model() -> ChatDeepSeek | ChatOpenAI:
    """创建最终回答用的聊天模型。

    项目里已有 DeepSeek 配置，所以优先使用 ChatDeepSeek；
    如果没有 DEEPSEEK_API_KEY，才回退到 OpenAI-compatible 配置。
    """

    # 第 1 步：优先读取 DeepSeek 专用 API Key。
    # 这样不会受 OPENAI_BASE_URL 配成 /anthropic 的影响。
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    temperature = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2"))
    if deepseek_key:
        # ChatDeepSeek 是 langchain-deepseek 提供的模型封装。
        return ChatDeepSeek(
            model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            api_key=deepseek_key,
            temperature=temperature,
            timeout=30,
            max_retries=1,
        )

    # 第 2 步：没有 DeepSeek key 时，回退到 OpenAI-compatible 客户端。
    # 这适合你接其它兼容 OpenAI Chat Completions 的服务。
    api_key = os.getenv("OPENAI_API_KEY")
    base_url = os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")
    model = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")

    if not api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY 或 DEEPSEEK_API_KEY，无法调用 DeepSeek。")

    # 第 3 步：这里返回的是 LangChain Runnable 模型对象，
    # 后面可以直接接在 LCEL 链上。
    return ChatOpenAI(
        api_key=api_key,
        base_url=base_url,
        model=model,
        temperature=temperature,
    )


def build_rag_chain(model: ChatOpenAI | ChatDeepSeek | None = None):
    """构建 LCEL 链：输入 dict -> prompt -> model -> 字符串输出。

    LCEL 的 `|` 可以理解为流水线：前一步输出会传给后一步。
    """

    # 第 1 步：定义 prompt 模板。
    # system 消息放全局规则，human 消息放本轮问题和检索资料。
    prompt = ChatPromptTemplate.from_messages(
        [
            ("system", SYSTEM_PROMPT),
            (
                "human",
                "问题：{question}\n\n参考资料：\n{context}\n\n请基于参考资料回答。",
            ),
        ]
    )

    # 第 2 步：如果测试传入了假模型，就用假模型；
    # 否则用 get_chat_model() 创建真实模型。
    chat_model = model or get_chat_model()

    # 第 3 步：构建 LCEL 流水线。
    # invoke 时传入 {"question": "...", "context": "..."}。
    return (
        {
            # itemgetter 从 invoke 传入的 dict 中取字段。
            "question": itemgetter("question"),
            "context": itemgetter("context"),
        }
        # 第 4 步：把 question/context 填到 prompt 模板里。
        | prompt
        # 第 5 步：把格式化后的消息交给模型。
        | chat_model
        # 第 6 步：把模型返回的 AIMessage 解析成普通字符串。
        | StrOutputParser()
    )


def answer_with_context(question: str, documents: Sequence[Document]) -> str:
    """用检索到的文档作为上下文，让模型生成最终回答。"""

    # 第 1 步：把多个 Document 拼成一段参考资料字符串。
    context = format_documents(documents)

    # 第 2 步：创建 RAG 问答链。
    chain = build_rag_chain()

    # 第 3 步：执行链。
    # 这里的 dict key 必须和 build_rag_chain 里的 itemgetter 名字一致。
    return chain.invoke({"question": question, "context": context})

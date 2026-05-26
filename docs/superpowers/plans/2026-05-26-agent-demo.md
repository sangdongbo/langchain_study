# Agent Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an independent `agent_demo/` teaching project that demonstrates a Streamlit Agent workspace with tools, middleware logs, RAG service boundaries, vector store integration, and mock tool routing.

**Architecture:** The project is isolated under `agent_demo/` and shares only root dependencies and `.env`. Streamlit calls `ReactAgent`, which routes requests to mock tools or `RagSummarizeService`; RAG code depends on `VectorStoreService` and `model.factory`, while middleware records prompt, tool, and model events.

**Tech Stack:** Python 3.14, Streamlit, LangChain core, Chroma integration code, DeepSeek/OpenAI-compatible chat models, pytest for pure unit tests, `python -m compileall` for syntax verification.

---

## Files And Responsibilities

- Create `agent_demo/__init__.py`: package marker.
- Create `agent_demo/app.py`: Streamlit UI only.
- Create `agent_demo/README.md`: usage and architecture notes.
- Create `agent_demo/config/__init__.py`: package marker.
- Create `agent_demo/config/settings.py`: environment and model settings.
- Create `agent_demo/data/sample_docs/agent_overview.md`: sample document for manual demos.
- Create `agent_demo/model/__init__.py`: package marker.
- Create `agent_demo/model/factory.py`: chat model and embedding factory.
- Create `agent_demo/prompts/agent_system.md`: general Agent prompt.
- Create `agent_demo/prompts/rag_summary.md`: RAG summary prompt.
- Create `agent_demo/rag/__init__.py`: package marker.
- Create `agent_demo/rag/vector_store.py`: document conversion, local hash embeddings, chunking, Chroma adapter.
- Create `agent_demo/rag/rag_service.py`: retrieval, answer, and summarization service.
- Create `agent_demo/tools/__init__.py`: package marker.
- Create `agent_demo/tools/agent_tools.py`: mock tools and RAG tool entry.
- Create `agent_demo/utils/__init__.py`: package marker.
- Create `agent_demo/utils/file_handler.py`: upload decoding and text cleanup.
- Create `agent_demo/utils/logger_handler.py`: log entry model and log store helpers.
- Create `agent_demo/utils/path_tools.py`: stable project paths.
- Create `agent_demo/utils/prompt_loader.py`: prompt file loading.
- Create `agent_demo/middleware.py`: tool/model/prompt logging wrappers.
- Create `agent_demo/react_agent.py`: rule-based Agent orchestration.
- Create `tests/test_agent_demo_utils.py`: pure tests for utils and prompts.
- Create `tests/test_agent_demo_agent.py`: pure tests for middleware, tools, and routing with fake RAG service.

Database safety: Do not run tests or commands that create, read, or write ChromaDB. Unit tests must use pure functions or fake objects only. Manual `streamlit run agent_demo/app.py` is allowed only for user-driven page verification and may write Chroma if the user uploads files.

---

### Task 1: Project Skeleton, Settings, Utilities, Prompts

**Files:**
- Create: `agent_demo/__init__.py`
- Create: `agent_demo/config/__init__.py`
- Create: `agent_demo/config/settings.py`
- Create: `agent_demo/utils/__init__.py`
- Create: `agent_demo/utils/path_tools.py`
- Create: `agent_demo/utils/logger_handler.py`
- Create: `agent_demo/utils/file_handler.py`
- Create: `agent_demo/utils/prompt_loader.py`
- Create: `agent_demo/prompts/agent_system.md`
- Create: `agent_demo/prompts/rag_summary.md`
- Create: `agent_demo/data/sample_docs/agent_overview.md`
- Create: `tests/test_agent_demo_utils.py`

- [ ] **Step 1: Write pure utility tests**

Create `tests/test_agent_demo_utils.py`:

```python
from __future__ import annotations

from pathlib import Path

import pytest

from agent_demo.config.settings import load_settings
from agent_demo.utils.file_handler import UploadedText, clean_text, decode_uploaded_bytes
from agent_demo.utils.logger_handler import LogStore, make_log
from agent_demo.utils.path_tools import AGENT_DEMO_ROOT, chroma_dir, prompt_path
from agent_demo.utils.prompt_loader import load_prompt


def test_paths_resolve_inside_agent_demo() -> None:
    assert AGENT_DEMO_ROOT.name == "agent_demo"
    assert chroma_dir() == AGENT_DEMO_ROOT / "chroma_db"
    assert prompt_path("agent_system.md") == AGENT_DEMO_ROOT / "prompts" / "agent_system.md"


def test_logger_store_keeps_recent_entries() -> None:
    store = LogStore(max_entries=2)
    store.add(make_log("one", "first"))
    store.add(make_log("two", "second"))
    store.add(make_log("three", "third"))

    rendered = store.render_lines()

    assert len(rendered) == 2
    assert "two：second" in rendered[0]
    assert "three：third" in rendered[1]


def test_clean_text_collapses_excess_blank_lines() -> None:
    assert clean_text("  第一段\n\n\n\n第二段  ") == "第一段\n\n第二段"


def test_decode_uploaded_bytes_prefers_utf8() -> None:
    uploaded = decode_uploaded_bytes("demo.md", "你好".encode("utf-8"))

    assert uploaded == UploadedText(name="demo.md", text="你好", encoding="utf-8")


def test_decode_uploaded_bytes_falls_back_to_gb18030() -> None:
    uploaded = decode_uploaded_bytes("demo.txt", "中文".encode("gb18030"))

    assert uploaded.name == "demo.txt"
    assert uploaded.text == "中文"
    assert uploaded.encoding == "gb18030"


def test_load_prompt_reads_existing_prompt() -> None:
    text = load_prompt("agent_system.md")

    assert "教学型智能体" in text


def test_load_prompt_reports_missing_prompt() -> None:
    with pytest.raises(FileNotFoundError, match="缺少 prompt 文件"):
        load_prompt("missing.md")


def test_load_settings_uses_deepseek_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "deepseek-key")
    monkeypatch.setenv("DEEPSEEK_MODEL", "deepseek-chat")
    monkeypatch.setenv("DEEPSEEK_TEMPERATURE", "0.3")

    settings = load_settings()

    assert settings.chat_provider == "deepseek"
    assert settings.chat_model == "deepseek-chat"
    assert settings.temperature == 0.3


def test_load_settings_falls_back_to_openai(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_API_KEY", "openai-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")

    settings = load_settings()

    assert settings.chat_provider == "openai"
    assert settings.chat_model == "gpt-test"
    assert settings.openai_base_url == "https://example.test/v1"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_agent_demo_utils.py -q
```

Expected: FAIL because `agent_demo` modules do not exist yet. This command is safe because the test file only imports pure utilities and does not touch ChromaDB.

- [ ] **Step 3: Create package markers**

Create empty files:

```text
agent_demo/__init__.py
agent_demo/config/__init__.py
agent_demo/utils/__init__.py
```

- [ ] **Step 4: Implement settings**

Create `agent_demo/config/settings.py`:

```python
from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentDemoSettings:
    chat_provider: str
    chat_api_key: str | None
    chat_model: str
    openai_base_url: str | None
    embedding_provider: str
    embedding_model: str
    temperature: float


def load_settings() -> AgentDemoSettings:
    deepseek_key = os.getenv("DEEPSEEK_API_KEY")
    temperature = float(os.getenv("DEEPSEEK_TEMPERATURE", "0.2"))

    if deepseek_key:
        return AgentDemoSettings(
            chat_provider="deepseek",
            chat_api_key=deepseek_key,
            chat_model=os.getenv("DEEPSEEK_MODEL", "deepseek-chat"),
            openai_base_url=None,
            embedding_provider=os.getenv("RAG_EMBEDDING_PROVIDER", "local").lower(),
            embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
            temperature=temperature,
        )

    return AgentDemoSettings(
        chat_provider="openai",
        chat_api_key=os.getenv("OPENAI_API_KEY"),
        chat_model=os.getenv("OPENAI_MODEL", "gpt-4.1-mini"),
        openai_base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1"),
        embedding_provider=os.getenv("RAG_EMBEDDING_PROVIDER", "local").lower(),
        embedding_model=os.getenv("OPENAI_EMBEDDING_MODEL", "text-embedding-3-small"),
        temperature=temperature,
    )
```

- [ ] **Step 5: Implement path utilities**

Create `agent_demo/utils/path_tools.py`:

```python
from __future__ import annotations

from pathlib import Path


AGENT_DEMO_ROOT = Path(__file__).resolve().parents[1]


def chroma_dir() -> Path:
    return AGENT_DEMO_ROOT / "chroma_db"


def sample_docs_dir() -> Path:
    return AGENT_DEMO_ROOT / "data" / "sample_docs"


def prompt_path(filename: str) -> Path:
    return AGENT_DEMO_ROOT / "prompts" / filename
```

- [ ] **Step 6: Implement logger utilities**

Create `agent_demo/utils/logger_handler.py`:

```python
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass(frozen=True)
class LogEntry:
    stage: str
    message: str
    timestamp: str

    def render(self) -> str:
        return f"[{self.timestamp}] {self.stage}：{self.message}"


@dataclass
class LogStore:
    max_entries: int = 80
    entries: list[LogEntry] = field(default_factory=list)

    def add(self, entry: LogEntry) -> None:
        self.entries.append(entry)
        if len(self.entries) > self.max_entries:
            self.entries = self.entries[-self.max_entries :]

    def render_lines(self) -> list[str]:
        return [entry.render() for entry in self.entries]

    def clear(self) -> None:
        self.entries.clear()


def make_log(stage: str, message: str) -> LogEntry:
    return LogEntry(
        stage=stage,
        message=message,
        timestamp=datetime.now().strftime("%H:%M:%S"),
    )
```

- [ ] **Step 7: Implement file utilities**

Create `agent_demo/utils/file_handler.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class UploadedText:
    name: str
    text: str
    encoding: str


def clean_text(text: str) -> str:
    stripped = text.strip()
    return re.sub(r"\n{3,}", "\n\n", stripped)


def decode_uploaded_bytes(name: str, raw: bytes) -> UploadedText:
    try:
        return UploadedText(name=name, text=clean_text(raw.decode("utf-8")), encoding="utf-8")
    except UnicodeDecodeError:
        return UploadedText(
            name=name,
            text=clean_text(raw.decode("gb18030", errors="ignore")),
            encoding="gb18030",
        )
```

- [ ] **Step 8: Implement prompt loader**

Create `agent_demo/utils/prompt_loader.py`:

```python
from __future__ import annotations

from agent_demo.utils.path_tools import prompt_path


def load_prompt(filename: str) -> str:
    path = prompt_path(filename)
    if not path.exists():
        raise FileNotFoundError(f"缺少 prompt 文件：{path}")
    return path.read_text(encoding="utf-8").strip()
```

- [ ] **Step 9: Add prompts and sample document**

Create `agent_demo/prompts/agent_system.md`:

```markdown
你是一个教学型智能体，用于演示 Agent 项目如何组织工具、RAG、向量库、中间件和页面。

回答要求：
- 优先使用中文。
- 如果调用了工具，请用自然语言解释工具结果。
- 如果使用了知识库资料，请说明依据来自检索片段。
- 如果资料不足，请明确说明没有找到足够依据。
```

Create `agent_demo/prompts/rag_summary.md`:

```markdown
请基于给定参考资料完成总结。

要求：
- 用中文输出。
- 先给 3 条以内要点。
- 再给一段简短总结。
- 不要编造参考资料之外的事实。
```

Create `agent_demo/data/sample_docs/agent_overview.md`:

```markdown
# 智能体项目说明

这个示例项目用于展示一个教学型智能体的基础结构。页面层负责交互，Agent 层负责编排，工具层负责外部能力，RAG 层负责知识库检索，模型工厂负责统一创建模型。

中间件用于记录 prompt 切换、工具调用和模型调用前后的日志。这样学习者可以观察一次用户提问如何经过不同模块，最终生成回答。
```

- [ ] **Step 10: Run utility tests**

Run:

```powershell
python -m pytest tests/test_agent_demo_utils.py -q
```

Expected: PASS. These tests do not touch ChromaDB or any external API.

- [ ] **Step 11: Commit Task 1**

Run:

```powershell
git add agent_demo tests/test_agent_demo_utils.py
git commit -m "feat(agent-demo): add project utilities"
```

---

### Task 2: Model Factory And Vector Store Pure Logic

**Files:**
- Create: `agent_demo/model/__init__.py`
- Create: `agent_demo/model/factory.py`
- Create: `agent_demo/rag/__init__.py`
- Create: `agent_demo/rag/vector_store.py`
- Modify: `tests/test_agent_demo_utils.py`

- [ ] **Step 1: Extend tests for embeddings and pure document helpers**

Append to `tests/test_agent_demo_utils.py`:

```python
from langchain_core.documents import Document

from agent_demo.model.factory import create_chat_model
from agent_demo.rag.vector_store import (
    IndexingResult,
    LocalHashEmbeddings,
    documents_from_uploads,
    file_md5,
    format_documents,
    split_documents,
)


def test_local_hash_embeddings_are_deterministic() -> None:
    embeddings = LocalHashEmbeddings(dimensions=32)

    first = embeddings.embed_query("智能体")
    second = embeddings.embed_query("智能体")

    assert first == second
    assert len(first) == 32


def test_documents_from_uploads_adds_metadata() -> None:
    docs = documents_from_uploads([UploadedText(name="a.md", text="内容", encoding="utf-8")])

    assert len(docs) == 1
    assert docs[0].page_content == "内容"
    assert docs[0].metadata["source"] == "a.md"
    assert docs[0].metadata["suffix"] == ".md"
    assert docs[0].metadata["file_md5"] == file_md5("内容")


def test_split_documents_keeps_metadata() -> None:
    docs = [Document(page_content="第一段。" * 80, metadata={"source": "a.md"})]

    chunks = split_documents(docs, chunk_size=60, chunk_overlap=10)

    assert len(chunks) > 1
    assert all(chunk.metadata["source"] == "a.md" for chunk in chunks)


def test_format_documents_includes_sources() -> None:
    docs = [Document(page_content="知识点", metadata={"source": "a.md"})]

    formatted = format_documents(docs)

    assert "来源：a.md" in formatted
    assert "知识点" in formatted


def test_indexing_result_summary_mentions_skipped_files() -> None:
    result = IndexingResult(added_chunks=2, skipped_files=["a.md"], indexed_files=[])

    assert result.summary() == "写入 2 个文本块，跳过重复文件：a.md"


def test_create_chat_model_reports_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="缺少 OPENAI_API_KEY 或 DEEPSEEK_API_KEY"):
        create_chat_model()
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_agent_demo_utils.py -q
```

Expected: FAIL because model and vector store modules do not exist.

- [ ] **Step 3: Create package markers**

Create empty files:

```text
agent_demo/model/__init__.py
agent_demo/rag/__init__.py
```

- [ ] **Step 4: Implement model factory**

Create `agent_demo/model/factory.py`:

```python
from __future__ import annotations

from langchain_deepseek import ChatDeepSeek
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

from agent_demo.config.settings import AgentDemoSettings, load_settings
from agent_demo.rag.vector_store import LocalHashEmbeddings


def create_chat_model(settings: AgentDemoSettings | None = None) -> ChatDeepSeek | ChatOpenAI:
    current = settings or load_settings()
    if not current.chat_api_key:
        raise RuntimeError("缺少 OPENAI_API_KEY 或 DEEPSEEK_API_KEY，无法调用聊天模型。")

    if current.chat_provider == "deepseek":
        return ChatDeepSeek(
            model=current.chat_model,
            api_key=current.chat_api_key,
            temperature=current.temperature,
            timeout=30,
            max_retries=1,
        )

    return ChatOpenAI(
        api_key=current.chat_api_key,
        base_url=current.openai_base_url,
        model=current.chat_model,
        temperature=current.temperature,
    )


def create_embeddings(settings: AgentDemoSettings | None = None):
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
```

- [ ] **Step 5: Implement vector store pure helpers and Chroma adapter**

Create `agent_demo/rag/vector_store.py`:

```python
from __future__ import annotations

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
    added_chunks: int
    skipped_files: list[str]
    indexed_files: list[tuple[str, str]]

    def summary(self) -> str:
        message = f"写入 {self.added_chunks} 个文本块"
        if self.skipped_files:
            message += "，跳过重复文件：" + "、".join(self.skipped_files)
        return message


class LocalHashEmbeddings(Embeddings):
    def __init__(self, dimensions: int = 512) -> None:
        self.dimensions = dimensions

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self._embed(text) for text in texts]

    def embed_query(self, text: str) -> list[float]:
        return self._embed(text)

    def _embed(self, text: str) -> list[float]:
        vector = [0.0] * self.dimensions
        counts = Counter(self._tokenize(text))
        for token, count in counts.items():
            digest = blake2b(token.encode("utf-8"), digest_size=8).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            sign = 1.0 if digest[4] % 2 == 0 else -1.0
            vector[index] += sign * float(count)
        norm = sqrt(sum(value * value for value in vector))
        if norm == 0:
            return vector
        return [value / norm for value in vector]

    @staticmethod
    def _tokenize(text: str) -> list[str]:
        normalized = text.lower()
        words = re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]", normalized)
        return words or list(normalized.strip())


def file_md5(text: str) -> str:
    return md5(text.encode("utf-8")).hexdigest()


def documents_from_uploads(files: Iterable[UploadedText]) -> list[Document]:
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
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""],
    )
    return splitter.split_documents(list(documents))


def chunk_ids(documents: Sequence[Document]) -> list[str]:
    ids: list[str] = []
    for index, doc in enumerate(documents):
        digest = doc.metadata.get("file_md5") or file_md5(doc.page_content)
        doc.metadata["file_md5"] = digest
        doc.metadata["chunk_index"] = index
        ids.append(f"{digest}-chunk-{index}")
    return ids


def format_documents(documents: Sequence[Document]) -> str:
    if not documents:
        return "未检索到相关资料。"

    formatted: list[str] = []
    for index, doc in enumerate(documents, start=1):
        source = doc.metadata.get("source", "未知来源")
        formatted.append(f"[{index}] 来源：{source}\n{doc.page_content.strip()}")
    return "\n\n".join(formatted)


class VectorStoreService:
    def __init__(
        self,
        persist_directory: Path | str | None = None,
        collection_name: str = DEFAULT_COLLECTION_NAME,
        embeddings: Embeddings | None = None,
    ) -> None:
        self.persist_directory = Path(persist_directory) if persist_directory else chroma_dir()
        self.collection_name = collection_name
        self.embeddings = embeddings or LocalHashEmbeddings()

    def get_store(self):
        if Chroma is None:
            raise RuntimeError("缺少 langchain-chroma 依赖，请先安装 langchain-chroma。")
        self.persist_directory.mkdir(parents=True, exist_ok=True)
        return Chroma(
            collection_name=self.collection_name,
            embedding_function=self.embeddings,
            persist_directory=str(self.persist_directory),
        )

    def load_documents(self, documents: Sequence[Document]) -> IndexingResult:
        if not documents:
            return IndexingResult(added_chunks=0, skipped_files=[], indexed_files=[])

        vector_store = self.get_store()
        new_documents: list[Document] = []
        skipped_files: list[str] = []
        indexed_files: list[tuple[str, str]] = []

        for document in documents:
            digest = document.metadata.get("file_md5") or file_md5(document.page_content)
            source = document.metadata.get("source", "未知文件")
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
        return self.get_store().similarity_search(query, k=k)
```

- [ ] **Step 6: Run pure tests**

Run:

```powershell
python -m pytest tests/test_agent_demo_utils.py -q
```

Expected: PASS. These tests do not instantiate `VectorStoreService.get_store()` and do not read or write ChromaDB.

- [ ] **Step 7: Commit Task 2**

Run:

```powershell
git add agent_demo/model agent_demo/rag tests/test_agent_demo_utils.py
git commit -m "feat(agent-demo): add model and vector helpers"
```

---

### Task 3: RAG Service With Fake-Friendly Interfaces

**Files:**
- Create: `agent_demo/rag/rag_service.py`
- Modify: `tests/test_agent_demo_utils.py`

- [ ] **Step 1: Add RAG service tests with fakes**

Append to `tests/test_agent_demo_utils.py`:

```python
from langchain_core.runnables import RunnableLambda

from agent_demo.rag.rag_service import RagSummarizeService


class FakeVectorStoreService:
    def retrieve(self, query: str, k: int = 4) -> list[Document]:
        return [Document(page_content=f"{query} 的资料", metadata={"source": "fake.md"})]


def test_rag_service_retrieve_docs_uses_vector_store() -> None:
    service = RagSummarizeService(vector_store=FakeVectorStoreService())

    docs = service.retrieve_docs("智能体", k=2)

    assert docs[0].page_content == "智能体 的资料"


def test_rag_service_answer_uses_context_and_question() -> None:
    model = RunnableLambda(lambda prompt_value: "基于资料回答")
    service = RagSummarizeService(vector_store=FakeVectorStoreService(), model=model)

    answer = service.answer("智能体是什么？")

    assert answer == "基于资料回答"


def test_rag_service_summarize_uses_summary_prompt() -> None:
    model = RunnableLambda(lambda prompt_value: "总结结果")
    service = RagSummarizeService(vector_store=FakeVectorStoreService(), model=model)

    answer = service.rag_summarize("智能体")

    assert answer == "总结结果"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_agent_demo_utils.py -q
```

Expected: FAIL because `agent_demo.rag.rag_service` does not exist.

- [ ] **Step 3: Implement RAG service**

Create `agent_demo/rag/rag_service.py`:

```python
from __future__ import annotations

from typing import Protocol, Sequence

from langchain_core.documents import Document
from langchain_core.output_parsers import StrOutputParser
from langchain_core.prompts import ChatPromptTemplate

from agent_demo.model.factory import create_chat_model
from agent_demo.rag.vector_store import VectorStoreService, format_documents
from agent_demo.utils.prompt_loader import load_prompt


class RetrieverService(Protocol):
    def retrieve(self, query: str, k: int = 4) -> list[Document]:
        ...


class RagSummarizeService:
    def __init__(self, vector_store: RetrieverService | None = None, model=None) -> None:
        self.vector_store = vector_store or VectorStoreService()
        self.model = model or create_chat_model()

    def retrieve_docs(self, question: str, k: int = 4) -> list[Document]:
        return self.vector_store.retrieve(question, k=k)

    def answer(self, question: str, k: int = 4) -> str:
        docs = self.retrieve_docs(question, k=k)
        context = format_documents(docs)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", load_prompt("agent_system.md")),
                ("human", "问题：{question}\n\n参考资料：\n{context}\n\n请基于参考资料回答。"),
            ]
        )
        chain = prompt | self.model | StrOutputParser()
        return chain.invoke({"question": question, "context": context})

    def rag_summarize(self, query: str, k: int = 4) -> str:
        docs = self.retrieve_docs(query, k=k)
        context = format_documents(docs)
        prompt = ChatPromptTemplate.from_messages(
            [
                ("system", load_prompt("rag_summary.md")),
                ("human", "总结主题：{query}\n\n参考资料：\n{context}"),
            ]
        )
        chain = prompt | self.model | StrOutputParser()
        return chain.invoke({"query": query, "context": context})

    @staticmethod
    def sources_for_display(documents: Sequence[Document]) -> list[dict[str, str]]:
        return [
            {
                "source": str(doc.metadata.get("source", "未知来源")),
                "content": doc.page_content.strip(),
            }
            for doc in documents
        ]
```

- [ ] **Step 4: Run tests**

Run:

```powershell
python -m pytest tests/test_agent_demo_utils.py -q
```

Expected: PASS. Fake vector store avoids ChromaDB access.

- [ ] **Step 5: Commit Task 3**

Run:

```powershell
git add agent_demo/rag/rag_service.py tests/test_agent_demo_utils.py
git commit -m "feat(agent-demo): add rag service"
```

---

### Task 4: Middleware, Tools, And Agent Routing

**Files:**
- Create: `agent_demo/middleware.py`
- Create: `agent_demo/tools/__init__.py`
- Create: `agent_demo/tools/agent_tools.py`
- Create: `agent_demo/react_agent.py`
- Create: `tests/test_agent_demo_agent.py`

- [ ] **Step 1: Write Agent tests with fake RAG service**

Create `tests/test_agent_demo_agent.py`:

```python
from __future__ import annotations

from langchain_core.documents import Document

from agent_demo.middleware import monitor_tool, report_prompt_switch
from agent_demo.react_agent import ReactAgent
from agent_demo.tools.agent_tools import (
    generate_external_data,
    get_current_month,
    get_user_id,
    get_user_location,
    get_weather,
)
from agent_demo.utils.logger_handler import LogStore


class FakeRagService:
    def __init__(self) -> None:
        self.last_question = ""

    def retrieve_docs(self, question: str, k: int = 4) -> list[Document]:
        self.last_question = question
        return [Document(page_content="片段内容", metadata={"source": "fake.md"})]

    def answer(self, question: str, k: int = 4) -> str:
        self.last_question = question
        return f"RAG回答：{question}"

    def rag_summarize(self, query: str, k: int = 4) -> str:
        self.last_question = query
        return f"总结：{query}"


def test_mock_tools_return_structured_results() -> None:
    assert get_user_id()["data"]["user_id"] == "U1001"
    assert get_user_location()["data"]["city"] == "上海"
    assert "month" in get_current_month()["data"]
    assert get_weather("北京")["data"]["location"] == "北京"
    assert generate_external_data("销售")["data"]["topic"] == "销售"


def test_middleware_records_tool_call() -> None:
    logs = LogStore()

    result = monitor_tool(logs, "demo_tool", {"a": 1}, lambda: {"ok": True})

    assert result == {"ok": True}
    assert "工具 demo_tool 参数" in logs.render_lines()[0]
    assert "工具 demo_tool 完成" in logs.render_lines()[1]


def test_report_prompt_switch_records_prompt() -> None:
    logs = LogStore()

    report_prompt_switch(logs, "rag_summary")

    assert "切换到 rag_summary" in logs.render_lines()[0]


def test_agent_routes_weather_to_tool() -> None:
    logs = LogStore()
    agent = ReactAgent(rag_service=FakeRagService(), logs=logs)

    response = agent.execute("帮我查一下北京天气")

    assert response.answer.startswith("北京天气")
    assert response.route == "tool:get_weather"


def test_agent_routes_summary_to_rag_summary() -> None:
    agent = ReactAgent(rag_service=FakeRagService(), logs=LogStore())

    response = agent.execute("总结一下智能体项目")

    assert response.answer == "总结：总结一下智能体项目"
    assert response.route == "rag:summarize"


def test_agent_routes_default_to_rag_answer() -> None:
    agent = ReactAgent(rag_service=FakeRagService(), logs=LogStore())

    response = agent.execute("智能体是什么？")

    assert response.answer == "RAG回答：智能体是什么？"
    assert response.route == "rag:answer"
    assert response.sources[0]["source"] == "fake.md"
```

- [ ] **Step 2: Run tests to verify failure**

Run:

```powershell
python -m pytest tests/test_agent_demo_agent.py -q
```

Expected: FAIL because middleware, tools, and agent modules do not exist.

- [ ] **Step 3: Implement middleware**

Create `agent_demo/middleware.py`:

```python
from __future__ import annotations

from collections.abc import Callable
from typing import Any

from agent_demo.utils.logger_handler import LogStore, make_log


def monitor_tool(logs: LogStore, tool_name: str, arguments: dict[str, Any], call: Callable[[], Any]) -> Any:
    logs.add(make_log("工具", f"工具 {tool_name} 参数：{arguments}"))
    try:
        result = call()
    except Exception as exc:
        logs.add(make_log("工具", f"工具 {tool_name} 失败：{exc}"))
        raise
    logs.add(make_log("工具", f"工具 {tool_name} 完成：{_summarize_result(result)}"))
    return result


def log_before_model(logs: LogStore, prompt_name: str, context: str) -> None:
    logs.add(make_log("模型", f"调用模型前：prompt={prompt_name}，上下文长度={len(context)}"))


def report_prompt_switch(logs: LogStore, prompt_name: str) -> None:
    logs.add(make_log("Prompt", f"切换到 {prompt_name}"))


def _summarize_result(result: Any) -> str:
    text = str(result)
    if len(text) <= 120:
        return text
    return text[:117] + "..."
```

- [ ] **Step 4: Implement mock tools**

Create `agent_demo/tools/__init__.py`:

```python
from __future__ import annotations
```

Create `agent_demo/tools/agent_tools.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Any


def get_user_id() -> dict[str, Any]:
    return {"source": "mock_tool", "data": {"user_id": "U1001", "name": "演示用户"}}


def get_user_location() -> dict[str, Any]:
    return {"source": "mock_tool", "data": {"city": "上海", "district": "浦东新区"}}


def get_current_month() -> dict[str, Any]:
    now = datetime.now()
    return {"source": "mock_tool", "data": {"month": now.strftime("%Y-%m"), "month_number": now.month}}


def get_weather(location: str = "上海") -> dict[str, Any]:
    return {
        "source": "mock_tool",
        "data": {
            "location": location,
            "condition": "多云",
            "temperature": "24°C",
            "suggestion": "适合进行智能体项目学习。",
        },
    }


def generate_external_data(topic: str) -> dict[str, Any]:
    return {
        "source": "mock_tool",
        "data": {
            "topic": topic,
            "items": [f"{topic} 指标 A", f"{topic} 指标 B", f"{topic} 指标 C"],
        },
    }
```

- [ ] **Step 5: Implement ReactAgent**

Create `agent_demo/react_agent.py`:

```python
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from agent_demo.middleware import monitor_tool, report_prompt_switch
from agent_demo.rag.rag_service import RagSummarizeService
from agent_demo.tools.agent_tools import (
    generate_external_data,
    get_current_month,
    get_user_id,
    get_user_location,
    get_weather,
)
from agent_demo.utils.logger_handler import LogStore, make_log


@dataclass(frozen=True)
class AgentResponse:
    answer: str
    route: str
    sources: list[dict[str, str]] = field(default_factory=list)
    tool_result: dict[str, Any] | None = None


class ReactAgent:
    def __init__(self, rag_service: Any | None = None, logs: LogStore | None = None, retrieval_k: int = 4) -> None:
        self.rag_service = rag_service or RagSummarizeService()
        self.logs = logs or LogStore()
        self.retrieval_k = retrieval_k

    def execute(self, message: str) -> AgentResponse:
        text = message.strip()
        self.logs.add(make_log("用户", text))

        if any(keyword in text for keyword in ("总结", "概括", "摘要")):
            return self._summarize(text)
        if "天气" in text:
            return self._weather(text)
        if any(keyword in text for keyword in ("位置", "在哪", "哪里")):
            return self._location()
        if any(keyword in text.lower() for keyword in ("用户", "user_id", "userid")):
            return self._user_id()
        if any(keyword in text for keyword in ("月份", "当前月")):
            return self._current_month()
        if any(keyword in text for keyword in ("外部数据", "生成数据", "模拟数据")):
            return self._external_data(text)
        return self._rag_answer(text)

    def execute_stream(self, message: str) -> list[str]:
        response = self.execute(message)
        return [response.answer]

    def _summarize(self, text: str) -> AgentResponse:
        report_prompt_switch(self.logs, "rag_summary")
        answer = self.rag_service.rag_summarize(text, k=self.retrieval_k)
        docs = self.rag_service.retrieve_docs(text, k=self.retrieval_k)
        return AgentResponse(answer=answer, route="rag:summarize", sources=self._sources(docs))

    def _rag_answer(self, text: str) -> AgentResponse:
        report_prompt_switch(self.logs, "agent_system")
        answer = self.rag_service.answer(text, k=self.retrieval_k)
        docs = self.rag_service.retrieve_docs(text, k=self.retrieval_k)
        return AgentResponse(answer=answer, route="rag:answer", sources=self._sources(docs))

    def _weather(self, text: str) -> AgentResponse:
        location = self._extract_location(text) or "上海"
        result = monitor_tool(self.logs, "get_weather", {"location": location}, lambda: get_weather(location))
        data = result["data"]
        answer = f"{data['location']}天气：{data['condition']}，温度 {data['temperature']}。{data['suggestion']}"
        return AgentResponse(answer=answer, route="tool:get_weather", tool_result=result)

    def _location(self) -> AgentResponse:
        result = monitor_tool(self.logs, "get_user_location", {}, get_user_location)
        data = result["data"]
        answer = f"当前演示用户位置：{data['city']} {data['district']}。"
        return AgentResponse(answer=answer, route="tool:get_user_location", tool_result=result)

    def _user_id(self) -> AgentResponse:
        result = monitor_tool(self.logs, "get_user_id", {}, get_user_id)
        data = result["data"]
        answer = f"当前用户：{data['name']}，用户 ID：{data['user_id']}。"
        return AgentResponse(answer=answer, route="tool:get_user_id", tool_result=result)

    def _current_month(self) -> AgentResponse:
        result = monitor_tool(self.logs, "get_current_month", {}, get_current_month)
        data = result["data"]
        answer = f"当前月份是 {data['month']}，月份数字为 {data['month_number']}。"
        return AgentResponse(answer=answer, route="tool:get_current_month", tool_result=result)

    def _external_data(self, text: str) -> AgentResponse:
        result = monitor_tool(self.logs, "generate_external_data", {"topic": text}, lambda: generate_external_data(text))
        data = result["data"]
        answer = "已生成模拟外部数据：" + "、".join(data["items"])
        return AgentResponse(answer=answer, route="tool:generate_external_data", tool_result=result)

    @staticmethod
    def _extract_location(text: str) -> str | None:
        match = re.search(r"([\u4e00-\u9fff]{2,8})天气", text)
        if match:
            return match.group(1).replace("一下", "").replace("查询", "").replace("查看", "")
        return None

    @staticmethod
    def _sources(documents) -> list[dict[str, str]]:
        return [
            {
                "source": str(doc.metadata.get("source", "未知来源")),
                "content": doc.page_content.strip(),
            }
            for doc in documents
        ]
```

- [ ] **Step 6: Run Agent tests**

Run:

```powershell
python -m pytest tests/test_agent_demo_agent.py -q
```

Expected: PASS. These tests use fake RAG service and do not touch ChromaDB.

- [ ] **Step 7: Run all agent demo pure tests**

Run:

```powershell
python -m pytest tests/test_agent_demo_utils.py tests/test_agent_demo_agent.py -q
```

Expected: PASS. These tests do not touch databases, migrations, seeders, or ChromaDB persistence.

- [ ] **Step 8: Commit Task 4**

Run:

```powershell
git add agent_demo tests/test_agent_demo_agent.py tests/test_agent_demo_utils.py
git commit -m "feat(agent-demo): add tools and agent routing"
```

---

### Task 5: Streamlit App And README

**Files:**
- Create: `agent_demo/app.py`
- Create: `agent_demo/README.md`

- [ ] **Step 1: Create Streamlit app**

Create `agent_demo/app.py`:

```python
from __future__ import annotations

import sys
from html import escape
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from agent_demo.rag.rag_service import RagSummarizeService
from agent_demo.rag.vector_store import VectorStoreService, documents_from_uploads
from agent_demo.react_agent import ReactAgent
from agent_demo.utils.file_handler import decode_uploaded_bytes
from agent_demo.utils.logger_handler import LogStore, make_log
from agent_demo.utils.path_tools import chroma_dir


st.set_page_config(page_title="综合智能体教学项目", page_icon="AI", layout="wide")
load_dotenv(override=True)


def inject_styles() -> None:
    st.markdown(
        """
        <style>
        .stApp { background: #101116; color: #f7f7fb; }
        [data-testid="stHeader"], [data-testid="stToolbar"], #MainMenu, footer { display: none; }
        [data-testid="stSidebar"] { background: #20222c; border-right: 1px solid rgba(255,255,255,.08); }
        [data-testid="stSidebar"] * { color: #f4f4f8; }
        .block-container { max-width: 1180px; padding-top: 42px; }
        .agent-title { font-size: 34px; font-weight: 800; margin-bottom: 6px; }
        .agent-subtitle { color: #aeb7c8; margin-bottom: 20px; }
        .tag-row { display: flex; flex-wrap: wrap; gap: 8px; margin-bottom: 22px; }
        .tag { border: 1px solid rgba(255,255,255,.12); border-radius: 999px; padding: 6px 10px; color: #cbd5e1; font-size: 13px; }
        .answer-box, .source-box, .log-box {
            background: #171a22; border: 1px solid rgba(255,255,255,.08); border-radius: 8px;
            padding: 14px 16px; line-height: 1.7;
        }
        .source-box { margin: 8px 0; background: #12151d; }
        .log-box { font-family: Consolas, monospace; color: #b7c0d4; font-size: 13px; }
        textarea, input { background: #171a22 !important; color: #f7f7fb !important; }
        .stButton > button {
            border-radius: 8px; border: 1px solid rgba(255,255,255,.12);
            background: #343746; color: #fff; min-height: 40px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def get_logs() -> LogStore:
    if "agent_demo_logs" not in st.session_state:
        st.session_state.agent_demo_logs = LogStore()
    return st.session_state.agent_demo_logs


def render_logs(logs: LogStore) -> None:
    lines = logs.render_lines()
    if not lines:
        st.markdown('<div class="log-box">暂无日志。</div>', unsafe_allow_html=True)
        return
    st.markdown(
        '<div class="log-box">' + "<br>".join(escape(line) for line in lines[-18:]) + "</div>",
        unsafe_allow_html=True,
    )


def main() -> None:
    inject_styles()
    logs = get_logs()
    st.session_state.setdefault("agent_demo_answer", "")
    st.session_state.setdefault("agent_demo_sources", [])
    st.session_state.setdefault("agent_demo_route", "")

    with st.sidebar:
        st.caption("智能体控制台")
        uploaded_files = st.file_uploader(
            "上传 txt / markdown 文档",
            type=["txt", "md", "markdown"],
            accept_multiple_files=True,
        )
        retrieval_k = st.slider("检索片段数量", min_value=1, max_value=8, value=4)
        st.caption(f"向量库路径：{chroma_dir()}")

        if st.button("写入知识库", use_container_width=True):
            if not uploaded_files:
                st.warning("请先上传至少一个文档。")
            else:
                try:
                    uploads = [decode_uploaded_bytes(file.name, file.getvalue()) for file in uploaded_files]
                    documents = documents_from_uploads(uploads)
                    result = VectorStoreService().load_documents(documents)
                    logs.add(make_log("入库", result.summary()))
                    st.success(result.summary())
                except Exception as exc:
                    logs.add(make_log("错误", str(exc)))
                    st.error(str(exc))

        if st.button("清空日志", use_container_width=True):
            logs.clear()
            st.rerun()

        st.markdown("#### 运行日志")
        render_logs(logs)

    st.markdown('<div class="agent-title">综合智能体教学项目</div>', unsafe_allow_html=True)
    st.markdown(
        '<div class="agent-subtitle">演示 Agent 编排、工具调用、RAG 检索、Prompt 切换、中间件日志和 Streamlit 页面如何协同工作。</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="tag-row"><span class="tag">Agent</span><span class="tag">Tools</span><span class="tag">RAG</span><span class="tag">ChromaDB</span><span class="tag">Middleware Logs</span></div>',
        unsafe_allow_html=True,
    )

    question = st.text_area(
        "输入问题",
        placeholder="例如：总结一下智能体项目；帮我查一下北京天气；智能体项目由哪些模块组成？",
        height=96,
    )

    if st.button("运行智能体"):
        if not question.strip():
            st.warning("请输入问题。")
        else:
            try:
                rag_service = RagSummarizeService(vector_store=VectorStoreService())
                agent = ReactAgent(rag_service=rag_service, logs=logs, retrieval_k=retrieval_k)
                response = agent.execute(question)
                st.session_state.agent_demo_answer = response.answer
                st.session_state.agent_demo_sources = response.sources
                st.session_state.agent_demo_route = response.route
            except Exception as exc:
                logs.add(make_log("错误", str(exc)))
                st.error(str(exc))

    if st.session_state.agent_demo_answer:
        st.markdown(f"#### 回答 · `{escape(st.session_state.agent_demo_route)}`")
        st.markdown(
            f'<div class="answer-box">{escape(st.session_state.agent_demo_answer).replace(chr(10), "<br>")}</div>',
            unsafe_allow_html=True,
        )

    if st.session_state.agent_demo_sources:
        st.markdown("#### 检索片段")
        for index, source in enumerate(st.session_state.agent_demo_sources, start=1):
            st.markdown(
                f'<div class="source-box"><strong>[{index}] {escape(source["source"])}</strong><br>{escape(source["content"]).replace(chr(10), "<br>")}</div>',
                unsafe_allow_html=True,
            )


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Create README**

Create `agent_demo/README.md`:

```markdown
# 综合智能体教学项目

这是一个独立的智能体教学项目，用于演示 Agent 项目常见模块如何协同工作：

- `app.py`：Streamlit 页面。
- `react_agent.py`：规则路由版 Agent 编排。
- `tools/agent_tools.py`：教学用 mock 工具。
- `middleware.py`：工具、prompt、模型调用日志。
- `rag/rag_service.py`：RAG 问答和总结服务。
- `rag/vector_store.py`：文档切分、去重、ChromaDB 接入。
- `model/factory.py`：聊天模型和 embedding 创建。
- `utils/`：路径、文件、日志、prompt 加载工具。

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

embedding 默认使用本地 hash embedding，方便课堂演示。如果要切换为 OpenAI-compatible embedding：

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
```

- [ ] **Step 3: Run syntax check**

Run:

```powershell
python -m compileall agent_demo
```

Expected: PASS. This does not touch ChromaDB.

- [ ] **Step 4: Run pure tests**

Before running, confirm the two test files only use pure utilities or fake RAG service:

```powershell
Select-String -Path tests/test_agent_demo_utils.py,tests/test_agent_demo_agent.py -Pattern "VectorStoreService\\(|load_documents\\(|get_store\\(|similarity_search\\(|Chroma|artisan|migrate|seed|RefreshDatabase|DatabaseMigrations|DatabaseTransactions"
```

Expected: no matches that instantiate real `VectorStoreService()` or touch ChromaDB. Then run:

```powershell
python -m pytest tests/test_agent_demo_utils.py tests/test_agent_demo_agent.py -q
```

Expected: PASS.

- [ ] **Step 5: Commit Task 5**

Run:

```powershell
git add agent_demo/app.py agent_demo/README.md
git commit -m "feat(agent-demo): add streamlit workspace"
```

---

### Task 6: Final Verification

**Files:**
- No new files expected.

- [ ] **Step 1: Inspect relevant tests for database safety**

Run:

```powershell
Select-String -Path tests/test_agent_demo_utils.py,tests/test_agent_demo_agent.py -Pattern "VectorStoreService\\(|load_documents\\(|get_store\\(|similarity_search\\(|Chroma|artisan|migrate|seed|RefreshDatabase|DatabaseMigrations|DatabaseTransactions"
```

Expected: no real ChromaDB or database access paths are exercised by tests.

- [ ] **Step 2: Run pure tests**

Run:

```powershell
python -m pytest tests/test_agent_demo_utils.py tests/test_agent_demo_agent.py -q
```

Expected: PASS.

- [ ] **Step 3: Run syntax verification**

Run:

```powershell
python -m compileall agent_demo
```

Expected: PASS.

- [ ] **Step 4: Check git status**

Run:

```powershell
git status --short
```

Expected: only unrelated pre-existing user changes remain, or no changes if all task commits are complete.

---

## Self-Review

Spec coverage:

- Independent `agent_demo/` project: Tasks 1-5.
- Streamlit teaching workspace: Task 5.
- Mock tools: Task 4.
- Middleware logs: Task 4.
- RAG service and vector store boundaries: Tasks 2-3.
- Model factory: Task 2.
- Prompt files and prompt loader: Task 1.
- Sample document: Task 1.
- Validation without database commands: Tasks 1-6.

Placeholder scan: The plan contains no deferred implementation placeholders. Each code-producing step includes exact file content.

Type consistency: The plan uses `LogStore`, `UploadedText`, `VectorStoreService`, `RagSummarizeService`, `ReactAgent`, and `AgentResponse` consistently across tasks.

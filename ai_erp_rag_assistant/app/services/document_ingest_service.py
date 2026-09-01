"""RAG 同步文档解析和 Chunk 准备服务。"""

from __future__ import annotations

import csv
import json
from html.parser import HTMLParser
from dataclasses import dataclass
from io import BytesIO, StringIO
from pathlib import Path
from typing import Any
from zipfile import BadZipFile, ZipFile
from xml.etree import ElementTree
from hashlib import sha256

from ai_erp_rag_assistant.scripts.ingest_pdf import infer_title, split_text


class DocumentParseError(ValueError):
    """文档无法解析为文本页面时抛出的异常。"""


@dataclass(frozen=True)
class ParsedPage:
    """解析后保留原始页码的一段文档文本。"""

    page: int
    text: str


_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".html", ".htm"}
_DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def parse_document(content: bytes, source: str) -> tuple[list[ParsedPage], list[int]]:
    """提取文本，并在格式支持时保留原始页码。"""

    if not content:
        raise DocumentParseError("文档内容为空")
    suffix = Path(source).suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(content)
    if suffix == ".docx":
        return _parse_docx(content)
    if suffix == ".json":
        return [ParsedPage(page=1, text=_parse_json_text(content))], []
    if suffix == ".csv":
        return [ParsedPage(page=1, text=_parse_csv_text(content))], []
    if suffix in {".html", ".htm"}:
        return [ParsedPage(page=1, text=_parse_html_text(content))], []
    if suffix == ".xml":
        return [ParsedPage(page=1, text=_parse_xml_text(content))], []
    if suffix in _TEXT_SUFFIXES or not suffix:
        return [ParsedPage(page=1, text=_decode_text(content))], []
    raise DocumentParseError(
        "暂不支持该文档格式，请使用 PDF、DOCX、TXT、Markdown、JSON 或 CSV"
    )


def build_chunk_rows(
    content: bytes,
    *,
    company_id: str,
    source: str,
    knowledge_base_key: str = "",
    department: str = "",
    version: str = "",
    effective_date: str = "",
    permission_tags: list[str] | None = None,
    title: str = "",
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> tuple[list[dict[str, Any]], list[int]]:
    """解析并切分一个文档，生成可写入 Milvus 的 Chunk 行。

    Embedding 统一交给 ``MilvusService.upsert_chunks``，保证所有导入路径
    使用相同的向量维度和 Collection 校验。
    """

    company_id = company_id.strip()
    source = source.strip()
    if not company_id:
        raise DocumentParseError("company_id 不能为空")
    if not source:
        raise DocumentParseError("source 不能为空")
    if not 100 <= chunk_size <= 4000:
        raise DocumentParseError("chunk_size 必须为 100..4000")
    if not 0 <= chunk_overlap < chunk_size:
        raise DocumentParseError("chunk_overlap 必须小于 chunk_size")

    # 解析器负责保留格式可提供的页码；扫描件空页在这里统一收集。
    pages, empty_pages = parse_document(content, source)
    knowledge_key = knowledge_base_key.strip() or "default"
    fallback_title = title.strip() or Path(source).name or source
    tags = [str(item).strip() for item in (permission_tags or []) if str(item).strip()]
    rows: list[dict[str, Any]] = []
    # 每页独立切分，避免一个 Chunk 跨页导致引用页码失真。
    for parsed_page in pages:
        page_text = parsed_page.text.strip()
        if not page_text:
            empty_pages.append(parsed_page.page)
            continue
        chunks = split_text(page_text, chunk_size, chunk_overlap)
        for chunk_number, chunk in enumerate(chunks, start=1):
            # 内容参与哈希，文档修改后生成新 ID；相同内容重试保持稳定。
            digest = sha256(
                f"{source}:{version}:{parsed_page.page}:{chunk_number}:{chunk}".encode()
            ).hexdigest()[:32]
            rows.append(
                {
                    "chunk_id": f"{company_id}:{knowledge_key}:{digest}",
                    "text": chunk,
                    "source": source,
                    "page": parsed_page.page,
                    "title": infer_title(chunk, fallback_title),
                    "company_id": company_id,
                    "department": department.strip(),
                    "version": version.strip(),
                    "effective_date": effective_date.strip(),
                    "is_active": True,
                    "permission_tags": tags,
                }
            )
    if not rows:
        # 所有支持格式最终都走同一个无文本错误，便于前端提示 OCR。
        raise DocumentParseError("文档没有可提取文本；扫描件请先生成文字层")
    return rows, sorted(set(empty_pages))


def _parse_pdf(content: bytes) -> tuple[list[ParsedPage], list[int]]:
    try:
        from pypdf import PdfReader

        reader = PdfReader(BytesIO(content))
        pages = [ParsedPage(page=index, text=page.extract_text() or "") for index, page in enumerate(reader.pages, 1)]
    except Exception as exc:
        raise DocumentParseError(f"PDF 解析失败：{exc}") from exc
    return pages, [page.page for page in pages if not page.text.strip()]


def _parse_docx(content: bytes) -> tuple[list[ParsedPage], list[int]]:
    """从 DOCX XML 中按文档顺序提取段落和表格行。"""
    try:
        with ZipFile(BytesIO(content)) as archive:
            xml = archive.read("word/document.xml")
        root = ElementTree.fromstring(xml)
    except (BadZipFile, KeyError, ElementTree.ParseError) as exc:
        raise DocumentParseError(f"DOCX 解析失败：{exc}") from exc
    blocks: list[str] = []
    body = root.find("w:body", _DOCX_NS)
    if body is None:
        return [ParsedPage(page=1, text="")], []
    for child in body:
        if child.tag == f"{{{_DOCX_NS['w']}}}p":
            text = _docx_element_text(child)
            if text:
                blocks.append(text)
        elif child.tag == f"{{{_DOCX_NS['w']}}}tbl":
            # 每个表格行保留为一条可检索记录，避免把单元格压平成难以阅读的段落流。
            for row in child.findall("w:tr", _DOCX_NS):
                cells = [_docx_element_text(cell) for cell in row.findall("w:tc", _DOCX_NS)]
                cells = [cell for cell in cells if cell]
                if cells:
                    blocks.append(" | ".join(cells))
    return [ParsedPage(page=1, text="\n".join(blocks))], []


def _docx_element_text(element: ElementTree.Element) -> str:
    return " ".join("".join(element.itertext()).split()).strip()


def _parse_json_text(content: bytes) -> str:
    decoded = _decode_text(content)
    try:
        value = json.loads(decoded)
    except json.JSONDecodeError as exc:
        raise DocumentParseError(f"JSON 解析失败：{exc}") from exc
    return json.dumps(value, ensure_ascii=False, indent=2)


def _parse_csv_text(content: bytes) -> str:
    """优先按表头输出字段值记录，无法识别表头时保留原始行。"""
    decoded = _decode_text(content)
    try:
        rows = list(csv.reader(StringIO(decoded)))
    except csv.Error as exc:
        raise DocumentParseError(f"CSV 解析失败：{exc}") from exc
    if not rows:
        return ""
    header = rows[0]
    if len(header) > 1:
        lines = []
        for row in rows[1:]:
            values = [f"{header[index]}: {value}" for index, value in enumerate(row) if index < len(header) and value]
            if values:
                lines.append("；".join(values))
        return "\n".join(lines) or " | ".join(header)
    return "\n".join(" | ".join(row) for row in rows if any(value.strip() for value in row))


class _VisibleTextParser(HTMLParser):
    _ignored = {"script", "style", "noscript", "template"}
    _block = {"address", "article", "br", "div", "h1", "h2", "h3", "h4", "li", "p", "section", "tr"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._ignored_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        """进入不可见节点时暂停收集，并为块级元素补换行。"""
        if tag in self._ignored:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag in self._block:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        """离开不可见节点时恢复收集，并结束块级元素。"""
        if tag in self._ignored and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag in self._block:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        """仅保存非隐藏节点中的可见文本。"""
        if not self._ignored_depth and data.strip():
            self.parts.append(data)


def _parse_html_text(content: bytes) -> str:
    parser = _VisibleTextParser()
    try:
        parser.feed(_decode_text(content))
        parser.close()
    except Exception as exc:
        raise DocumentParseError(f"HTML 解析失败：{exc}") from exc
    return "\n".join(line.strip() for line in "".join(parser.parts).splitlines() if line.strip())


def _parse_xml_text(content: bytes) -> str:
    try:
        root = ElementTree.fromstring(content)
    except ElementTree.ParseError as exc:
        raise DocumentParseError(f"XML 解析失败：{exc}") from exc
    return " ".join("".join(root.itertext()).split())


def _decode_text(content: bytes) -> str:
    # 有 BOM 时以 BOM 指定的编码为准；否则先尝试 UTF-8，再尝试兼容性更强的 GB18030。
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        return content.decode("utf-16")
    if content.startswith(b"\xef\xbb\xbf"):
        return content.decode("utf-8-sig")
    for encoding in ("utf-8", "gb18030", "utf-16"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    return content.decode("utf-8", errors="replace")

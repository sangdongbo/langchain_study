"""Synchronous document parsing and chunk preparation for RAG ingestion."""

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
    """Raised when a document cannot be parsed into text pages."""


@dataclass(frozen=True)
class ParsedPage:
    page: int
    text: str


_TEXT_SUFFIXES = {".txt", ".md", ".markdown", ".csv", ".json", ".xml", ".html", ".htm"}
_DOCX_NS = {"w": "http://schemas.openxmlformats.org/wordprocessingml/2006/main"}


def parse_document(content: bytes, source: str) -> tuple[list[ParsedPage], list[int]]:
    """Extract text while preserving page numbers where the format provides them."""

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
    """Parse and split one document into Milvus-ready rows.

    Embedding is deliberately performed by ``MilvusService.upsert_chunks`` so
    that every ingestion path shares the same vector dimension and collection
    validation.
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

    pages, empty_pages = parse_document(content, source)
    knowledge_key = knowledge_base_key.strip() or "default"
    fallback_title = title.strip() or Path(source).name or source
    tags = [str(item).strip() for item in (permission_tags or []) if str(item).strip()]
    rows: list[dict[str, Any]] = []
    for parsed_page in pages:
        page_text = parsed_page.text.strip()
        if not page_text:
            empty_pages.append(parsed_page.page)
            continue
        chunks = split_text(page_text, chunk_size, chunk_overlap)
        for chunk_number, chunk in enumerate(chunks, start=1):
            digest = sha256(
                f"{source}:{parsed_page.page}:{chunk_number}:{chunk}".encode()
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
            # Preserve each table row as one searchable record instead of
            # flattening cells into an unreadable paragraph stream.
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
        if tag in self._ignored:
            self._ignored_depth += 1
        elif not self._ignored_depth and tag in self._block:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._ignored and self._ignored_depth:
            self._ignored_depth -= 1
        elif not self._ignored_depth and tag in self._block:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
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
    # BOMs are authoritative; otherwise try UTF-8 before the permissive
    # GB18030 decoder, which can accept arbitrary binary-looking bytes.
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

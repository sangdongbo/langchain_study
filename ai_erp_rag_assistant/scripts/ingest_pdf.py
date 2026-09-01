"""识别本地 PDF，按页切分并输出带来源的 JSONL Chunk。

默认先停在“可审查的中间结果”；只有显式传入 ``--write-milvus`` 才会
生成 Embedding 并写入本项目 collection，避免误写入其他 collection。
"""

from __future__ import annotations

import json
import re
import sys
import argparse
from pathlib import Path

from pypdf import PdfReader

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
for import_root in (REPOSITORY_ROOT, PROJECT_ROOT):
    if str(import_root) not in sys.path:
        sys.path.insert(0, str(import_root))

from ai_erp_rag_assistant.app.config import get_settings


HEADING_PATTERN = re.compile(r"第[一二三四五六七八九十百零〇0-9]+[章节条]\s*[^。；]{0,50}")


def split_text(text: str, size: int, overlap: int) -> list[str]:
    """优先在标题或中文标点处切分文本，并保留指定重叠。"""
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        if end < len(normalized):
            window = normalized[start:end]
            minimum_break = max(int(size * 0.6), 1)
            punctuation_break = max(window.rfind(mark) for mark in ("。", "！", "？", "；")) + 1
            heading_breaks = [match.start() for match in HEADING_PATTERN.finditer(window)]
            heading_break = heading_breaks[-1] if heading_breaks else -1
            preferred_break = max(punctuation_break, heading_break)
            if preferred_break >= minimum_break:
                end = start + preferred_break
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def infer_title(text: str, fallback: str) -> str:
    """从 Chunk 中提取章节标题，未找到时使用文件名。"""
    match = HEADING_PATTERN.search(text)
    if match:
        return match.group(0).strip()
    return fallback


def document_metadata(pdf_path: Path, text: str, settings) -> dict[str, object]:
    """从文件名和首页文本推断版本、生效日期及租户元数据。"""
    version_match = re.search(r"(20\d{2})\s*年?\s*(?:修订版|版)", f"{pdf_path.stem} {text}")
    effective_match = re.search(
        r"生效日期\s*[:：]?\s*(20\d{2})\s*年\s*(\d{1,2})\s*月\s*(\d{1,2})\s*日",
        text,
    )
    effective_date = ""
    if effective_match:
        year, month, day = (int(item) for item in effective_match.groups())
        effective_date = f"{year:04d}-{month:02d}-{day:02d}"
    return {
        "company_id": settings.rag_company_id,
        "department": settings.rag_department,
        "version": version_match.group(1) if version_match else "",
        "effective_date": effective_date,
        "permission_tags": list(settings.rag_permission_tags),
    }


def extract_pdf(pdf_path: Path, settings) -> tuple[list[dict[str, object]], list[int]]:
    """按页解析 PDF 并生成可审查的 Milvus Chunk 行。"""
    reader = PdfReader(str(pdf_path))
    page_texts = [page.extract_text() or "" for page in reader.pages]
    # 版本和生效日期通常出现在文件名或前两页，避免扫描全文只为提取元数据。
    metadata = document_metadata(pdf_path, " ".join(page_texts[:2]), settings)
    rows: list[dict[str, object]] = []
    empty_pages: list[int] = []
    # 每页单独切分，输出 Chunk 的 page 可以直接用于引用和人工复核。
    for page_number, page_text in enumerate(page_texts, start=1):
        if not page_text.strip():
            empty_pages.append(page_number)
            continue
        for chunk_number, chunk in enumerate(
            split_text(page_text, settings.rag_chunk_size, settings.rag_chunk_overlap),
            start=1,
        ):
            rows.append(
                {
                    "chunk_id": f"{pdf_path.stem}_p{page_number:03d}_c{chunk_number:02d}",
                    "text": chunk,
                    "source": pdf_path.name,
                    "page": page_number,
                    "title": infer_title(chunk, pdf_path.stem),
                    "company_id": metadata["company_id"],
                    "department": metadata["department"],
                    "version": metadata["version"],
                    "effective_date": metadata["effective_date"],
                    "is_active": True,
                    "permission_tags": metadata["permission_tags"],
                }
            )
    return rows, empty_pages


def main() -> None:
    """生成 JSONL 和解析报告，仅在显式参数下写入 Milvus。"""
    parser = argparse.ArgumentParser(description="解析员工手册并可显式写入本项目 Milvus collection")
    parser.add_argument(
        "--write-milvus",
        action="store_true",
        help="在生成 JSONL 后，生成 Embedding 并写入 erp_knowledge_chunks；默认只生成 JSONL。",
    )
    args = parser.parse_args()
    settings = get_settings()
    pdfs = sorted(settings.rag_source_dir.glob("*.pdf"))
    if not pdfs:
        raise SystemExit(f"在 {settings.rag_source_dir} 下没有找到 PDF 文件")
    settings.rag_processed_dir.mkdir(parents=True, exist_ok=True)

    # 先汇总所有本地 PDF 的 Chunk 和空页报告，默认只生成可人工检查的中间文件。
    all_rows: list[dict[str, object]] = []
    report: list[dict[str, object]] = []
    for pdf_path in pdfs:
        rows, empty_pages = extract_pdf(pdf_path, settings)
        all_rows.extend(rows)
        report.append({"source": pdf_path.name, "chunks": len(rows), "empty_pages": empty_pages})

    output = settings.rag_processed_dir / "employee_handbook_2026_chunks.jsonl"
    output.write_text("\n".join(json.dumps(row, ensure_ascii=False) for row in all_rows), encoding="utf-8")
    report_path = settings.rag_processed_dir / "parse_report.json"
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"识别完成：{len(all_rows)} 个 Chunk")
    print(f"Chunk 输出：{output}")
    print(f"解析报告：{report_path}")
    if args.write_milvus:
        # 只有显式 --write-milvus 才加载外部服务并执行向量写入。
        from ai_erp_rag_assistant.app.services.milvus_service import milvus_service

        inserted = milvus_service.upsert_chunks(all_rows, company_id=settings.rag_company_id)
        print(f"Milvus 入库完成：{inserted} 个 Chunk，collection={settings.milvus_collection}")
    else:
        print("未写入 Milvus。复核 JSONL 后，如需入库请显式追加 --write-milvus。")


if __name__ == "__main__":
    main()

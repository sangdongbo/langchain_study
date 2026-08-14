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


def split_text(text: str, size: int, overlap: int) -> list[str]:
    normalized = re.sub(r"\s+", " ", text).strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(start + size, len(normalized))
        chunks.append(normalized[start:end])
        if end == len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def extract_pdf(pdf_path: Path, settings) -> tuple[list[dict[str, object]], list[int]]:
    reader = PdfReader(str(pdf_path))
    rows: list[dict[str, object]] = []
    empty_pages: list[int] = []
    for page_number, page in enumerate(reader.pages, start=1):
        page_text = page.extract_text() or ""
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
                    "title": None,
                    "company_id": "lanjing",
                    "department": "公共制度",
                    "version": "2026",
                    "effective_date": "2026-04-11",
                    "is_active": True,
                    "permission_tags": ["knowledge:employee_handbook"],
                }
            )
    return rows, empty_pages


def main() -> None:
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
        raise SystemExit(f"No PDF found under {settings.rag_source_dir}")
    settings.rag_processed_dir.mkdir(parents=True, exist_ok=True)

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
        from ai_erp_rag_assistant.app.services.milvus_service import milvus_service

        inserted = milvus_service.upsert_chunks(all_rows)
        print(f"Milvus 入库完成：{inserted} 个 Chunk，collection={settings.milvus_collection}")
    else:
        print("未写入 Milvus。复核 JSONL 后，如需入库请显式追加 --write-milvus。")


if __name__ == "__main__":
    main()

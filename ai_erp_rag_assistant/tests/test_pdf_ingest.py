from pathlib import Path

from scripts.ingest_pdf import extract_pdf


def test_employee_handbook_is_text_extractable():
    from ai_erp_rag_assistant.app.config import Settings

    pdf = Path(__file__).parents[1] / "data" / "knowledge" / "source" / "北京澜景科技有限公司员工手册（2026修订版）.pdf"
    settings = Settings()
    rows, empty_pages = extract_pdf(pdf, settings)

    assert pdf.exists()
    assert rows
    assert empty_pages == []
    assert all(row["source"] == pdf.name for row in rows)
    assert all(row["page"] >= 1 for row in rows)
    assert all(row["title"] for row in rows)
    assert all(row["version"] == "2026" for row in rows)
    assert all(row["effective_date"] == "2026-04-11" for row in rows)

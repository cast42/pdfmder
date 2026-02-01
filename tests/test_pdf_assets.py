from __future__ import annotations

from pathlib import Path

from pdfmder.pdfium_extract import extract_pdf_assets


def test_extract_pdf_assets_lengths_equal_page_count() -> None:
    root = Path(__file__).resolve().parents[1]
    pdf_path = root / "data" / "test.pdf"

    image_paths, page_texts, page_count = extract_pdf_assets(pdf_path)

    assert page_count > 0
    assert len(image_paths) == page_count
    assert len(page_texts) == page_count

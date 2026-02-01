from __future__ import annotations

from pathlib import Path

import pypdfium2 as pdfium

from pdfmder.pdfium_images import render_pdf_pages_to_images_tmp


def test_render_pages_returns_correct_page_count() -> None:
    root = Path(__file__).resolve().parents[1]
    pdf_path = root / "data" / "test.pdf"

    expected_pages = len(pdfium.PdfDocument(str(pdf_path)))

    with render_pdf_pages_to_images_tmp(pdf_path, dpi=72) as (paths, images, page_count):
        assert page_count == expected_pages
        assert len(paths) == expected_pages
        assert len(images) == expected_pages
        # The temp files should exist while in context
        assert all(p.exists() for p in paths)

    # After exiting context, temp paths should no longer exist
    assert all(not p.exists() for p in paths)

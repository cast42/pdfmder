"""PDFium-based extraction helpers."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

import logfire
import pypdfium2 as pdfium

from pdfmder.pdfium_images import render_pdf_pages_to_images_tmp


@contextmanager
def extract_pdf_assets_tmp(
    pdf_path: Path,
    *,
    dpi: int = 150,
) -> Iterator[tuple[list[Path], list[str], int]]:
    """Extract per-page assets from a PDF, keeping temporary images alive.

    Returns:
        (image_paths, page_texts, page_count)

    The image paths point to files in a temporary directory. They are valid only
    while inside the context manager.

    Text extraction uses the PDF text layer (no OCR).
    """
    pdf_path = Path(pdf_path)

    with logfire.span("pdfmder.extract_pdf_assets_tmp", pdf_path=str(pdf_path), dpi=dpi):
        with render_pdf_pages_to_images_tmp(pdf_path, dpi=dpi) as (image_paths, _pil_images, page_count):
            pdf = pdfium.PdfDocument(str(pdf_path))
            page_texts: list[str] = []

            for i in range(page_count):
                page = pdf[i]
                textpage = page.get_textpage()
                page_texts.append(textpage.get_text_range())

            # Invariant: one entry per page.
            assert len(image_paths) == page_count
            assert len(page_texts) == page_count

            yield image_paths, page_texts, page_count

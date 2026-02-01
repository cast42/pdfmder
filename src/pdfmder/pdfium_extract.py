from __future__ import annotations

from pathlib import Path

import logfire
import pypdfium2 as pdfium

from pdfmder.pdfium_images import render_pdf_pages_to_images_tmp


def extract_pdf_assets(pdf_path: Path) -> tuple[list[Path], list[str], int]:
    """Extract per-page assets from a PDF.

    Returns:
        image_paths: list[Path] - rendered page images (one per page)
        page_texts: list[str] - extracted text per page (one per page)
        page_count: int

    Notes:
        - Image paths live in a temporary directory. They will be deleted when the
          process exits the internal temp context (i.e., they are meant for immediate
          downstream processing inside a single call).
        - For scanned PDFs, text extraction may be empty (no OCR here).
    """
    pdf_path = Path(pdf_path)

    with logfire.span("pdfmder.extract_pdf_assets", pdf_path=str(pdf_path)):
        # Render images into a temporary directory and immediately extract text.
        with render_pdf_pages_to_images_tmp(pdf_path) as (image_paths, _pil_images, page_count):
            pdf = pdfium.PdfDocument(str(pdf_path))
            page_texts: list[str] = []
            for i in range(page_count):
                page = pdf[i]
                textpage = page.get_textpage()
                page_texts.append(textpage.get_text_range())

            # Invariant: one entry per page.
            assert len(image_paths) == page_count
            assert len(page_texts) == page_count

            # Return while tempdir is still alive.
            return image_paths, page_texts, page_count

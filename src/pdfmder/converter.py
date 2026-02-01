from __future__ import annotations

from pathlib import Path

import logfire
import pypdfium2 as pdfium


def extract_text_per_page(pdf_path: Path) -> list[str]:
    """Extract text per page from a (born-digital) PDF.

    Note: for scanned PDFs, the text layer may be empty; OCR is not performed here.
    """
    with logfire.span("pdfmder.extract_text_per_page", pdf_path=str(pdf_path)):
        pdf = pdfium.PdfDocument(str(pdf_path))
        pages: list[str] = []
        for i in range(len(pdf)):
            page = pdf[i]
            textpage = page.get_textpage()
            text = textpage.get_text_range()
            pages.append(text)
        return pages


def convert_pdf_to_markdown(pdf_path: Path) -> str:
    """Convert a PDF to Markdown.

    Current implementation: returns the extracted text and joins pages with a page break.
    For our test fixture we generate a PDF that contains the raw markdown source as text,
    which makes this conversion deterministic.
    """
    with logfire.span("pdfmder.convert_pdf_to_markdown", pdf_path=str(pdf_path)):
        pages = extract_text_per_page(pdf_path)
        # Keep it simple and stable.
        return "\n\n---\n\n".join(p.strip("\n") for p in pages).strip() + "\n"

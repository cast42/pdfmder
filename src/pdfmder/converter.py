from __future__ import annotations

from pathlib import Path

import logfire

from pdfmder.llm_markdown import PageMetrics, convert_to_markdown
from pdfmder.pdfium_extract import extract_pdf_assets_tmp


def convert_pdf_to_markdown(pdf_path: Path) -> tuple[str, list[PageMetrics]]:
    """Convert a PDF to Markdown page-by-page.

    For each page, we call an LLM (via Pydantic AI Gateway) with:
    - extracted text for prev/current/next pages
    - rendered images for prev/current/next pages
    - previous page's generated markdown

    The LLM returns Markdown for the current page.
    """
    with logfire.span("pdfmder.convert_pdf_to_markdown", pdf_path=str(pdf_path)):
        with extract_pdf_assets_tmp(pdf_path) as (image_paths, page_texts, page_count):
            logfire.info(
                "pdfmder.extract_pdf_assets.done", pages=page_count, images=len(image_paths), texts=len(page_texts)
            )

            md_pages: list[str] = []
            page_metrics: list[PageMetrics] = []
            prev_md: str | None = None

            for i in range(page_count):
                prev_text = page_texts[i - 1] if i > 0 else None
                prev_image = image_paths[i - 1] if i > 0 else None

                curr_text = page_texts[i]
                curr_image = image_paths[i]

                next_text = page_texts[i + 1] if i + 1 < page_count else None
                next_image = image_paths[i + 1] if i + 1 < page_count else None

                logfire.info(
                    "pdfmder.page.start",
                    page=i + 1,
                    pages=page_count,
                    has_prev=i > 0,
                    has_next=i + 1 < page_count,
                )

                md, metrics = convert_to_markdown(
                    prev_text=prev_text,
                    prev_image=prev_image,
                    curr_text=curr_text,
                    curr_image=curr_image,
                    next_text=next_text,
                    next_image=next_image,
                    prev_markdown=prev_md,
                )

                md_pages.append(md)
                page_metrics.append(metrics)
                prev_md = md

            return "\n\n---\n\n".join(p.strip("\n") for p in md_pages).strip() + "\n", page_metrics

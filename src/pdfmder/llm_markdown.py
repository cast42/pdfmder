"""LLM-backed Markdown conversion.

This module contains the page-level LLM call used by the PDF → Markdown pipeline.
"""

from __future__ import annotations

from pathlib import Path

import logfire
from pydantic_ai import Agent
from pydantic_ai.messages import ImageUrl


def convert_to_markdown(
    *,
    prev_text: str | None,
    prev_image: Path | None,
    curr_text: str,
    curr_image: Path,
    next_text: str | None,
    next_image: Path | None,
    prev_markdown: str | None,
) -> str:
    """Convert a single PDF page to Markdown using an LLM via Pydantic AI Gateway.

    Args correspond to the page context window. Images are provided as local files.

    Returns:
        Markdown for the current page.
    """
    # Read config from environment
    import os

    model_name = os.getenv("PDFMDER_MODEL", "gateway/openai:gpt-5")

    agent = Agent(model_name)

    prompt = (
        "You are converting a PDF page to well-structured Markdown. "
        "Return ONLY Markdown. Use ATX headings (#, ##, ###, ...). "
        "Preserve tables, lists, links, and structure as best as possible.\n\n"
        "You are given the extracted text and rendered images for the previous/current/next pages. "
        "Use surrounding pages to resolve heading levels and cross-page tables.\n\n"
        f"PREVIOUS PAGE MARKDOWN (if any):\n{prev_markdown or ''}\n\n"
        f"PREVIOUS PAGE TEXT (if any):\n{prev_text or ''}\n\n"
        f"CURRENT PAGE TEXT:\n{curr_text}\n\n"
        f"NEXT PAGE TEXT (if any):\n{next_text or ''}\n"
    )

    # Provide images as ImageUrl parts. force_download=True ensures local file is read and sent.
    parts: list[str | ImageUrl] = [prompt]

    def add_image(label: str, path: Path | None) -> None:
        if path is None:
            return
        parts.append(f"\n\n{label}:\n")
        parts.append(ImageUrl(url=path.as_uri(), force_download=True))

    add_image("PREVIOUS PAGE IMAGE", prev_image)
    add_image("CURRENT PAGE IMAGE", curr_image)
    add_image("NEXT PAGE IMAGE", next_image)

    with logfire.span(
        "pdfmder.llm.convert_to_markdown",
        model=model_name,
        has_prev=prev_text is not None,
        has_next=next_text is not None,
    ):
        result = agent.run_sync(parts)
        md = result.output
        logfire.info("pdfmder.llm.page_done", chars=len(md))
        return md.strip() + "\n"

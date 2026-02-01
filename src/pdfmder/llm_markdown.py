"""LLM-backed Markdown conversion.

This module contains the page-level LLM call used by the PDF → Markdown pipeline.
"""

from __future__ import annotations

from pathlib import Path

import logfire
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent


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
    import re

    # Default to direct OpenAI. Can be swapped to e.g. anthropic:..., google-gla:..., or gateway/openai:...
    model_name = os.getenv("PDFMDER_MODEL", "openai:gpt-5")
    allow_fallback = os.getenv("PDFMDER_ALLOW_FALLBACK", "1") != "0"

    def fallback_markdown(text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned + "\n"

    # Basic runtime validation for provider credentials.
    if model_name.startswith("openai:") and not os.getenv("OPENAI_API_KEY"):
        if allow_fallback:
            logfire.warning(
                "pdfmder.llm.fallback",
                reason="missing_openai_key",
                model=model_name,
            )
            return fallback_markdown(curr_text)
        raise RuntimeError(
            "OPENAI_API_KEY is required when PDFMDER_MODEL starts with 'openai:'. "
            "Set it in your environment or in a .env file (see .env.example)."
        )

    agent = Agent(model_name)

    prompt = (
        "You are converting a PDF page to precise, well-structured Markdown. "
        "Return ONLY Markdown (no prose, no code fences).\n\n"
        "Strict rules:\n"
        "1) Use ATX headings ONLY (#, ##, ###). No Setext headers.\n"
        "2) Preserve document structure: headings, paragraphs, lists, and numbering.\n"
        "3) Reconstruct tables using GitHub-flavored Markdown tables with a header row and separator row.\n"
        "   - Keep column counts consistent across all rows.\n"
        "   - If a table has no explicit header, infer a short header from context or use placeholders like 'Column 1'.\n"
        "4) Keep text content faithful; do not invent new content.\n"
        "5) Avoid repeating headers across pages unless the PDF explicitly repeats them.\n"
        "6) Use blank lines between block elements.\n\n"
        "You are given extracted text and rendered images for the previous/current/next pages. "
        "Use surrounding pages to resolve heading levels, list continuity, and cross-page tables.\n\n"
        f"PREVIOUS PAGE MARKDOWN (if any):\n{prev_markdown or ''}\n\n"
        f"PREVIOUS PAGE TEXT (if any):\n{prev_text or ''}\n\n"
        f"CURRENT PAGE TEXT:\n{curr_text}\n\n"
        f"NEXT PAGE TEXT (if any):\n{next_text or ''}\n"
    )

    # Provide images as ImageUrl parts. force_download=True ensures local file is read and sent.
    parts: list[str | BinaryContent] = [prompt]

    def add_image(label: str, path: Path | None) -> None:
        if path is None:
            return
        parts.append(f"\n\n{label}:\n")
        data = path.read_bytes()
        parts.append(BinaryContent(data=data, media_type="image/png"))

    add_image("PREVIOUS PAGE IMAGE", prev_image)
    add_image("CURRENT PAGE IMAGE", curr_image)
    add_image("NEXT PAGE IMAGE", next_image)

    with logfire.span(
        "pdfmder.llm.convert_to_markdown",
        model=model_name,
        has_prev=prev_text is not None,
        has_next=next_text is not None,
    ):
        try:
            result = agent.run_sync(parts)
        except Exception as exc:  # noqa: BLE001
            if allow_fallback:
                logfire.warning(
                    "pdfmder.llm.fallback",
                    reason="llm_error",
                    model=model_name,
                    error=str(exc),
                )
                return fallback_markdown(curr_text)
            raise

        md = result.output
        logfire.info("pdfmder.llm.page_done", chars=len(md))
        return md.strip() + "\n"

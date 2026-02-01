"""LLM-backed Markdown conversion.

This module contains the page-level LLM call used by the PDF → Markdown pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import logfire
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent


@dataclass(frozen=True)
class PageMetrics:
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    duration_s: float
    fallback: bool


def convert_to_markdown(
    *,
    prev_text: str | None,
    prev_image: Path | None,
    curr_text: str,
    curr_image: Path,
    next_text: str | None,
    next_image: Path | None,
    prev_markdown: str | None,
) -> tuple[str, PageMetrics]:
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
    force_openai = os.getenv("PDFMDER_FORCE_OPENAI", "1") != "0"
    if force_openai and model_name.startswith("gateway/openai:"):
        model_name = model_name.removeprefix("gateway/")
    allow_fallback = os.getenv("PDFMDER_ALLOW_FALLBACK", "1") != "0"

    def fallback_markdown(text: str) -> str:
        cleaned = text.strip()
        if not cleaned:
            return ""
        cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
        return cleaned + "\n"

    def extract_usage(result: object) -> tuple[int | None, int | None, int | None]:
        usage = getattr(result, "usage", None)
        if callable(usage):
            usage = usage()
        if usage is None:
            usage = getattr(result, "result_usage", None)
        if usage is None:
            usage = getattr(result, "usage_info", None)
        if usage is None and hasattr(result, "model_dump"):
            dump = result.model_dump()
            usage = dump.get("usage") or dump.get("result_usage") or dump.get("usage_info")

        def get_value(obj: object, *keys: str) -> int | None:
            for key in keys:
                if isinstance(obj, dict) and key in obj:
                    return obj[key]
                value = getattr(obj, key, None)
                if value is not None:
                    return value
            return None

        if usage is None:
            return None, None, None

        input_tokens = get_value(usage, "input_tokens", "prompt_tokens")
        output_tokens = get_value(usage, "output_tokens", "completion_tokens")
        total_tokens = get_value(usage, "total_tokens")
        return input_tokens, output_tokens, total_tokens

    start_time = perf_counter()

    # Basic runtime validation for provider credentials.
    if model_name.startswith("openai:") and not os.getenv("OPENAI_API_KEY"):
        if allow_fallback:
            logfire.warning(
                "pdfmder.llm.fallback",
                reason="missing_openai_key",
                model=model_name,
            )
            duration_s = perf_counter() - start_time
            return (
                fallback_markdown(curr_text),
                PageMetrics(
                    model=model_name,
                    input_tokens=None,
                    output_tokens=None,
                    total_tokens=None,
                    duration_s=duration_s,
                    fallback=True,
                ),
            )
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
                duration_s = perf_counter() - start_time
                return (
                    fallback_markdown(curr_text),
                    PageMetrics(
                        model=model_name,
                        input_tokens=None,
                        output_tokens=None,
                        total_tokens=None,
                        duration_s=duration_s,
                        fallback=True,
                    ),
                )
            raise

        md = result.output
        input_tokens, output_tokens, total_tokens = extract_usage(result)
        duration_s = perf_counter() - start_time
        logfire.info("pdfmder.llm.page_done", chars=len(md))
        return (
            md.strip() + "\n",
            PageMetrics(
                model=model_name,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=total_tokens,
                duration_s=duration_s,
                fallback=False,
            ),
        )

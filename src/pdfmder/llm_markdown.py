"""LLM-backed Markdown conversion.

This module contains the page-level LLM call used by the PDF → Markdown pipeline.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from time import perf_counter
from typing import cast

import logfire
from openai import AsyncOpenAI, RateLimitError
from pydantic_ai import Agent
from pydantic_ai.messages import BinaryContent
from pydantic_ai.models.openai import OpenAIResponsesModel, OpenAIResponsesModelSettings
from pydantic_ai.providers.openai import OpenAIProvider
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential


@dataclass(frozen=True)
class PageMetrics:
    model: str
    input_tokens: int | None
    output_tokens: int | None
    total_tokens: int | None
    duration_s: float
    fallback: bool


SYSTEM_PROMPT = (
    "You are a document conversion assistant. Convert ONLY the current PDF page into "
    "precise, high-quality Markdown. Preserve structure such as headings, tables, "
    "lists, bold text, and callouts. Use surrounding pages only for context; do not "
    "repeat their content. Return Markdown only—no explanations or code fences."
)


@lru_cache(maxsize=1)
def _get_openai_client() -> AsyncOpenAI:
    import os

    if os.getenv("AZURE_OPENAI_ENDPOINT"):
        api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        if not api_key:
            raise RuntimeError("AZURE_OPENAI_API_KEY must be set for Azure OpenAI access.")
        endpoint = os.environ["AZURE_OPENAI_ENDPOINT"].rstrip("/")
        api_version = os.environ.get("AZURE_OPENAI_API_VERSION", "preview")
        base_url = f"{endpoint}/openai/v1"
        return AsyncOpenAI(
            base_url=base_url,
            api_key=api_key,
            default_query={"api-version": api_version},
        )

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY must be set for OpenAI access.")
    base_url = os.environ.get("OPENAI_BASE_URL")
    return AsyncOpenAI(api_key=api_key, base_url=base_url)


@lru_cache(maxsize=4)
def _make_agent(model_name: str) -> Agent:
    client = _get_openai_client()
    provider = OpenAIProvider(openai_client=client)
    model = OpenAIResponsesModel(model_name, provider=provider)
    settings = OpenAIResponsesModelSettings()
    return Agent(model=model, system_prompt=SYSTEM_PROMPT, model_settings=settings)


@retry(
    retry=retry_if_exception_type(RateLimitError),
    stop=stop_after_attempt(6),
    wait=wait_exponential(multiplier=1, min=2, max=30),
)
def _run_agent_with_retry(agent: Agent, parts: list[str | BinaryContent]) -> object:
    return agent.run_sync(parts)


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
    """Convert a single PDF page to Markdown using OpenAI Responses via PydanticAI.

    Args correspond to the page context window. Images are provided as local files.

    Returns:
        Markdown for the current page.
    """
    # Read config from environment
    import os
    import re

    # Default to direct OpenAI. When AZURE_OPENAI_ENDPOINT is set, use deployment name.
    model_name = os.getenv("PDFMDER_MODEL", "gpt-5")
    if model_name.startswith("gateway/openai:"):
        model_name = model_name.removeprefix("gateway/openai:")
    if model_name.startswith("openai:"):
        model_name = model_name.removeprefix("openai:")
    if os.getenv("AZURE_OPENAI_ENDPOINT"):
        model_name = os.getenv("AZURE_OPENAI_DEPLOYMENT", model_name)
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
        if usage is None:
            model_dump = getattr(result, "model_dump", None)
            if callable(model_dump):
                dump = model_dump()
                if isinstance(dump, dict):
                    usage = dump.get("usage") or dump.get("result_usage") or dump.get("usage_info")

        def get_value(obj: object, *keys: str) -> int | None:
            for key in keys:
                if isinstance(obj, dict) and key in obj:
                    mapping = cast(dict[str, object], obj)
                    value = mapping.get(key)
                    return value if isinstance(value, int) else None
                value = getattr(obj, key, None)
                if isinstance(value, int):
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
    if os.getenv("AZURE_OPENAI_ENDPOINT") and not os.getenv("AZURE_OPENAI_API_KEY"):
        if allow_fallback:
            logfire.warning(
                "pdfmder.llm.fallback",
                reason="missing_azure_key",
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
        raise RuntimeError("AZURE_OPENAI_API_KEY must be set when using Azure OpenAI.")

    if not os.getenv("AZURE_OPENAI_ENDPOINT") and not os.getenv("OPENAI_API_KEY"):
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
        raise RuntimeError("OPENAI_API_KEY must be set for OpenAI access.")

    agent = _make_agent(model_name)

    def build_section(title: str, body: str | None) -> str:
        value = body if body else "None"
        return f"## {title}\n{value}"

    prompt = "\n\n".join(
        [
            "Convert ONLY the current PDF page into Markdown. "
            "Use OCR text and page images to reflect structure. "
            "Do NOT include content from other pages. Respond with Markdown only.",
            "Rules:\n"
            "- Use ATX headings only (#, ##, ###).\n"
            "- Preserve lists, numbering, and callouts.\n"
            "- Reconstruct tables using GitHub-flavored Markdown with a header row and separator.\n"
            "- Keep column counts consistent and do not invent content.",
            build_section("Previous Page Markdown", prev_markdown),
            build_section("Previous Page Text", prev_text),
            build_section("Current Page Text", curr_text),
            build_section("Next Page Text", next_text),
        ]
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
            result = _run_agent_with_retry(agent, parts)
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

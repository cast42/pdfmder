from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

import logfire
import pypdfium2 as pdfium
from PIL import Image


@contextmanager
def render_pdf_pages_to_images_tmp(
    pdf_path: Path,
    *,
    dpi: int = 150,
    image_format: str = "png",
) -> Iterator[tuple[list[Path], list[Image.Image], int]]:
    """Render each page of a PDF to an image in a temporary folder.

    Returns:
        (image_paths, pil_images, page_count)

    The temporary folder is cleaned up automatically when the context exits.

    Notes:
        - This is PDF *rendering* (page → pixels), not text extraction.
        - Paths are only valid while inside the context manager.
    """
    pdf_path = Path(pdf_path)

    with logfire.span("pdfmder.render_pages", pdf_path=str(pdf_path), dpi=dpi, image_format=image_format):
        pdf = pdfium.PdfDocument(str(pdf_path))
        page_count = len(pdf)

        with TemporaryDirectory(prefix="pdfmder-") as tmp:
            tmp_dir = Path(tmp)
            image_paths: list[Path] = []
            pil_images: list[Image.Image] = []

            scale = dpi / 72.0

            for i in range(page_count):
                page = pdf[i]
                bitmap = page.render(scale=scale)
                pil = bitmap.to_pil()

                out_path = tmp_dir / f"page-{i + 1:04d}.{image_format}"
                pil.save(out_path)

                image_paths.append(out_path)
                pil_images.append(pil)

            yield image_paths, pil_images, page_count

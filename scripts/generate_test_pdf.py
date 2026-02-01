from __future__ import annotations

"""Generate data/test.pdf from data/test.md.

We intentionally generate a PDF that contains the *raw markdown source as text*.
This makes it possible to round-trip via text extraction and compare with test.md.
"""

from pathlib import Path

from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas


def write_markdown_as_pdf(md_path: Path, pdf_path: Path) -> None:
    text = md_path.read_text(encoding="utf-8")

    c = canvas.Canvas(str(pdf_path), pagesize=letter)
    width, height = letter

    left_margin = 36
    top_margin = 36
    bottom_margin = 36

    font_name = "Courier"
    font_size = 9
    line_height = font_size * 1.2

    c.setFont(font_name, font_size)

    x = left_margin
    y = height - top_margin

    for line in text.splitlines():
        if y <= bottom_margin:
            c.showPage()
            c.setFont(font_name, font_size)
            y = height - top_margin

        c.drawString(x, y, line)
        y -= line_height

    c.save()


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    md_path = root / "data" / "test.md"
    pdf_path = root / "data" / "test.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown_as_pdf(md_path, pdf_path)


if __name__ == "__main__":
    main()

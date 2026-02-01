"""Generate data/test.pdf from data/test.md.

This renders the Markdown *visually* into a PDF (headings, lists, a long table, etc.).
It's intentionally a lightweight renderer (not a full Markdown implementation).
"""

from __future__ import annotations

from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.platypus import LongTable, Paragraph, SimpleDocTemplate, Spacer, TableStyle


def _parse_table(lines: list[str]) -> list[list[str]]:
    rows: list[list[str]] = []
    for line in lines:
        line = line.strip()
        if not (line.startswith("|") and line.endswith("|")):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        rows.append(cells)
    # drop separator row (---) if present
    if len(rows) >= 2 and all(set(c) <= {"-", ":"} for c in rows[1]):
        rows.pop(1)
    return rows


def write_markdown_as_pdf(md_path: Path, pdf_path: Path) -> None:
    md = md_path.read_text(encoding="utf-8")

    doc = SimpleDocTemplate(
        str(pdf_path), pagesize=letter, leftMargin=36, rightMargin=36, topMargin=36, bottomMargin=36
    )
    styles = getSampleStyleSheet()

    # Simple heading styles
    h_styles = {
        1: ParagraphStyle("H1", parent=styles["Heading1"], fontSize=20, spaceAfter=10),
        2: ParagraphStyle("H2", parent=styles["Heading2"], fontSize=16, spaceAfter=8),
        3: ParagraphStyle("H3", parent=styles["Heading3"], fontSize=14, spaceAfter=6),
        4: ParagraphStyle("H4", parent=styles["Heading4"], fontSize=12, spaceAfter=6),
        5: ParagraphStyle("H5", parent=styles["Heading5"], fontSize=11, spaceAfter=4),
        6: ParagraphStyle("H6", parent=styles["Heading6"], fontSize=10, spaceAfter=4),
    }

    story = []
    lines = md.splitlines()
    i = 0

    bullet_style = ParagraphStyle("Bullet", parent=styles["BodyText"], leftIndent=14, bulletIndent=6)

    while i < len(lines):
        line = lines[i].rstrip("\n")

        if not line.strip():
            i += 1
            continue

        # Headings
        if line.startswith("#"):
            level = len(line) - len(line.lstrip("#"))
            level = min(max(level, 1), 6)
            text = line[level:].strip()
            story.append(Paragraph(text, h_styles[level]))
            i += 1
            continue

        # Horizontal rule
        if line.strip() == "---":
            story.append(Spacer(1, 8))
            story.append(Paragraph("—" * 40, styles["BodyText"]))
            story.append(Spacer(1, 8))
            i += 1
            continue

        # Table block
        if line.strip().startswith("|"):
            table_lines = []
            while i < len(lines) and lines[i].strip().startswith("|"):
                table_lines.append(lines[i])
                i += 1
            rows = _parse_table(table_lines)
            if rows:
                tbl = LongTable(rows, repeatRows=1)
                tbl.setStyle(
                    TableStyle(
                        [
                            ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey),
                            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                            ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
                            ("VALIGN", (0, 0), (-1, -1), "TOP"),
                            ("LEFTPADDING", (0, 0), (-1, -1), 4),
                            ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                        ]
                    )
                )
                story.append(tbl)
                story.append(Spacer(1, 12))
            continue

        # Unordered list
        if line.lstrip().startswith("-"):
            while i < len(lines) and lines[i].lstrip().startswith("-"):
                item = lines[i].lstrip()[1:].strip()
                story.append(Paragraph(item, bullet_style, bulletText="•"))
                i += 1
            story.append(Spacer(1, 8))
            continue

        # Ordered list
        if line.strip()[:2].isdigit() and "." in line:
            # naive check for "1. foo"
            while i < len(lines):
                line_str = lines[i].strip()
                if len(line_str) < 3 or not line_str[0].isdigit() or line_str[1] != ".":
                    break
                item = line_str[2:].strip()
                story.append(Paragraph(item, bullet_style, bulletText=f"{line_str[0]}."))
                i += 1
            story.append(Spacer(1, 8))
            continue

        # Images (render as caption)
        if line.strip().startswith("!["):
            story.append(Paragraph(line.strip(), styles["Code"]))
            story.append(Spacer(1, 8))
            i += 1
            continue

        # Default paragraph (links will just render as text)
        story.append(Paragraph(line, styles["BodyText"]))
        story.append(Spacer(1, 6))
        i += 1

    doc.build(story)


def main() -> None:
    """CLI entry point to generate the test PDF."""
    root = Path(__file__).resolve().parents[1]
    md_path = root / "data" / "test.md"
    pdf_path = root / "data" / "test.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    write_markdown_as_pdf(md_path, pdf_path)


if __name__ == "__main__":
    main()

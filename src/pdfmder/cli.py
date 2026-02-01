from __future__ import annotations

from pathlib import Path

import logfire
import typer
from rich.console import Console
from rich.panel import Panel

from pdfmder.converter import convert_pdf_to_markdown

console = Console()

# Console-only by default; user can configure a token later.
logfire.configure(send_to_logfire=False)


def cli(
    pdf: Path = typer.Argument(..., help="Path to the PDF file to convert"),
    output: Path | None = typer.Option(None, "-o", "--output", help="Output markdown file path"),
) -> None:
    """pdfmder: convert PDF files to Markdown."""
    with logfire.span("pdfmder.cli", pdf=str(pdf), output=str(output) if output else None):
        pdf_path = pdf
        if not pdf_path.is_absolute():
            pdf_path = Path.cwd() / pdf_path

        if not pdf_path.exists():
            console.print(Panel.fit(f"File not found: {pdf_path}", title="pdfmder", style="red"))
            raise typer.Exit(code=1)

        if pdf_path.suffix.lower() != ".pdf":
            console.print(Panel.fit(f"Not a PDF: {pdf_path}", title="pdfmder", style="red"))
            raise typer.Exit(code=1)

        out_path = output
        if out_path is None:
            out_path = pdf_path.with_suffix(".md")
        elif not out_path.is_absolute():
            out_path = Path.cwd() / out_path

        logfire.info("pdfmder.convert.start", pdf=str(pdf_path), output=str(out_path))

        try:
            with console.status("Converting PDF → Markdown…", spinner="dots"):
                md = convert_pdf_to_markdown(pdf_path)
        except RuntimeError as e:
            console.print(Panel.fit(str(e), title="pdfmder", style="red"))
            raise typer.Exit(code=1)

        out_path.write_text(md, encoding="utf-8")
        logfire.info("pdfmder.convert.done", pdf=str(pdf_path), output=str(out_path), chars=len(md))

        console.print(Panel.fit(f"Wrote {out_path}", title="pdfmder", style="green"))


def run() -> None:
    """Console entry point."""
    typer.run(cli)


if __name__ == "__main__":
    run()

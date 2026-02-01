from __future__ import annotations

from pathlib import Path

import logfire
import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from pdfmder.converter import convert_pdf_to_markdown

console = Console()

# Console-only by default; user can configure a token later.
logfire.configure(send_to_logfire=False)
logfire.instrument_pydantic_ai()


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
            default_dir = Path.cwd() / "output"
            default_dir.mkdir(parents=True, exist_ok=True)
            out_path = default_dir / f"{pdf_path.stem}.md"
        elif not out_path.is_absolute():
            out_path = Path.cwd() / out_path

        if out_path.exists():
            stem = out_path.stem
            suffix = out_path.suffix
            parent = out_path.parent
            counter = 1
            while True:
                candidate = parent / f"{stem}-{counter}{suffix}"
                if not candidate.exists():
                    out_path = candidate
                    break
                counter += 1

        logfire.info("pdfmder.convert.start", pdf=str(pdf_path), output=str(out_path))

        try:
            with console.status("Converting PDF → Markdown…", spinner="dots"):
                md, metrics = convert_pdf_to_markdown(pdf_path)
        except RuntimeError as e:
            console.print(Panel.fit(str(e), title="pdfmder", style="red"))
            raise typer.Exit(code=1)

        out_path.write_text(md, encoding="utf-8")
        logfire.info("pdfmder.convert.done", pdf=str(pdf_path), output=str(out_path), chars=len(md))

        console.print(Panel.fit(f"Wrote {out_path}", title="pdfmder", style="green"))

        if metrics:
            table = Table(title="LLM usage per page")
            table.add_column("Page", justify="right")
            table.add_column("Input", justify="right")
            table.add_column("Output", justify="right")
            table.add_column("Total", justify="right")
            table.add_column("Time (s)", justify="right")
            table.add_column("Fallback", justify="center")

            def fmt_tokens(value: int | None) -> str:
                return "n/a" if value is None else str(value)

            def total_tokens_for_page() -> list[int]:
                totals: list[int] = []
                for item in metrics:
                    if item.total_tokens is not None:
                        totals.append(item.total_tokens)
                    else:
                        totals.append((item.input_tokens or 0) + (item.output_tokens or 0))
                return totals

            totals_per_page = total_tokens_for_page()

            for index, item in enumerate(metrics, start=1):
                table.add_row(
                    str(index),
                    fmt_tokens(item.input_tokens),
                    fmt_tokens(item.output_tokens),
                    fmt_tokens(totals_per_page[index - 1]),
                    f"{item.duration_s:.2f}",
                    "yes" if item.fallback else "no",
                )

            console.print(table)

            page_count = len(metrics)
            total_input = sum(item.input_tokens or 0 for item in metrics)
            total_output = sum(item.output_tokens or 0 for item in metrics)
            total_tokens = sum(totals_per_page)
            total_time = sum(item.duration_s for item in metrics)

            avg_input = total_input / page_count
            avg_output = total_output / page_count
            avg_tokens = total_tokens / page_count
            avg_time = total_time / page_count

            missing_tokens = sum(1 for item in metrics if item.input_tokens is None or item.output_tokens is None)

            summary_lines = [
                f"Total input tokens: {total_input}",
                f"Total output tokens: {total_output}",
                f"Total tokens: {total_tokens}",
                f"Average input tokens/page: {avg_input:.2f}",
                f"Average output tokens/page: {avg_output:.2f}",
                f"Average total tokens/page: {avg_tokens:.2f}",
                f"Total time: {total_time:.2f}s",
                f"Average time/page: {avg_time:.2f}s",
            ]
            if missing_tokens:
                summary_lines.append(
                    f"Token counts unavailable for {missing_tokens} page(s) (fallback or provider did not return usage)."
                )

            console.print(Panel.fit("\n".join(summary_lines), title="LLM totals", style="blue"))


def run() -> None:
    """Console entry point."""
    typer.run(cli)


if __name__ == "__main__":
    run()

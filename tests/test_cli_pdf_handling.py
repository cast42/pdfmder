from __future__ import annotations

from pathlib import Path

import typer
from typer.testing import CliRunner

from pdfmder.cli import cli

app = typer.Typer(add_completion=False)
app.command()(cli)


def ensure_test_pdf(project_root: Path) -> None:
    pdf_path = project_root / "data" / "test.pdf"
    if pdf_path.exists():
        return

    # Generate if missing
    import subprocess

    subprocess.check_call(["python3.14", str(project_root / "scripts" / "generate_test_pdf.py")])


def test_missing_file_errors(tmp_path: Path) -> None:
    runner = CliRunner()
    result = runner.invoke(app, [str(tmp_path / "missing.pdf")])
    assert result.exit_code != 0
    assert "File not found" in result.stdout


def test_wrong_suffix_errors(tmp_path: Path) -> None:
    f = tmp_path / "not_a_pdf.txt"
    f.write_text("x", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(app, [str(f)])
    assert result.exit_code != 0
    assert "Not a PDF" in result.stdout


def test_happy_path_writes_output_file(tmp_path: Path) -> None:
    """Smoke test: running the CLI produces a markdown file."""
    project_root = Path(__file__).resolve().parents[1]
    ensure_test_pdf(project_root)

    pdf_path = project_root / "data" / "test.pdf"
    out_path = tmp_path / "out.md"

    runner = CliRunner()
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, [str(pdf_path), "--output", str(out_path)])

    assert result.exit_code == 0
    assert out_path.exists()
    produced = out_path.read_text(encoding="utf-8").strip()
    assert produced
    # Should contain at least the first heading text
    assert "Heading 1" in produced

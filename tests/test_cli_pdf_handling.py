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


def test_happy_path_roundtrip_matches_test_md(tmp_path: Path) -> None:
    project_root = Path(__file__).resolve().parents[1]
    ensure_test_pdf(project_root)

    pdf_path = project_root / "data" / "test.pdf"
    expected_md = (project_root / "data" / "test.md").read_text(encoding="utf-8")

    out_path = tmp_path / "out.md"

    runner = CliRunner()
    # Run from tmp_path to ensure relative path logic is correct.
    with runner.isolated_filesystem(temp_dir=tmp_path):
        result = runner.invoke(app, [str(pdf_path), "--output", str(out_path)])

    assert result.exit_code == 0
    produced = out_path.read_text(encoding="utf-8")

    # Our converter adds a trailing newline; normalize.
    assert produced.strip() == expected_md.strip()

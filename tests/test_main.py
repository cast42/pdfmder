"""Tests for pdfmder CLI."""

from typer.testing import CliRunner

from pdfmder.cli import app


def test_cli_prints_hello_world() -> None:
    runner = CliRunner()
    result = runner.invoke(app, [])
    assert result.exit_code == 0
    assert "Hello world" in result.stdout

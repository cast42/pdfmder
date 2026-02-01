from __future__ import annotations

import typer

app = typer.Typer(add_completion=False)


@app.command()
def hello() -> None:
    """Print a friendly greeting (placeholder)."""
    typer.echo("Hello world")


def main() -> None:
    app()


if __name__ == "__main__":
    main()

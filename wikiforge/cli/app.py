"""The `wiki` Typer application entry point."""

from __future__ import annotations

import typer

app = typer.Typer(
    name="wiki",
    help="wikiforge — compile a personal knowledge base.",
    no_args_is_help=True,
)


@app.callback()
def callback() -> None:
    """wikiforge — compile a personal knowledge base."""


@app.command()
def version() -> None:
    """Print the wikiforge version."""
    from wikiforge import __version__

    typer.echo(__version__)


def main() -> None:
    """Console-script entry point."""
    app()

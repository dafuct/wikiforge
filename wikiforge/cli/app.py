"""The `wiki` Typer application entry point."""

from __future__ import annotations

import asyncio
from pathlib import Path

import typer

from wikiforge.paths import resolve_home

app = typer.Typer(
    name="wiki",
    help="wikiforge — compile a personal knowledge base.",
    no_args_is_help=True,
)

HomeOption = typer.Option(None, "--home", help="Wiki home directory (default: ~/wiki).")


@app.callback()
def callback() -> None:
    """wikiforge — compile a personal knowledge base."""


@app.command()
def version() -> None:
    """Print the wikiforge version."""
    from wikiforge import __version__

    typer.echo(__version__)


@app.command()
def init(
    name: str = typer.Argument(..., help="Display name for this wiki."),
    home: str | None = HomeOption,
) -> None:
    """Initialize a new wiki (config, database, topics directory)."""
    from wikiforge.services import init_wiki

    target = resolve_home(home)
    result: Path = asyncio.run(init_wiki(name, target))
    typer.echo(f"Initialized wiki {name!r} at {result}")


@app.command()
def ingest(
    target: str = typer.Argument(..., help="URL, PDF path, or text file to ingest."),
    home: str | None = HomeOption,
) -> None:
    """Ingest a source (URL, PDF, or file) into the wiki."""
    import httpx

    from wikiforge.config.settings import load_config
    from wikiforge.embed.factory import build_embedding_provider
    from wikiforge.services import ingest_source
    from wikiforge.storage.db import Database
    from wikiforge.storage.repository import Repository

    target_home = resolve_home(home)

    async def _run() -> tuple[str, bool]:
        cfg = load_config(target_home)
        db = await Database.open(target_home, dim=cfg.embedding.dim)
        try:
            embedder = build_embedding_provider(cfg, Repository(db))
            async with httpx.AsyncClient() as client:
                src, created = await ingest_source(
                    target_home, target, http_client=client, embedder=embedder, _db=db
                )
            return src.title, created
        finally:
            await db.close()

    title, created = asyncio.run(_run())
    verb = "Ingested" if created else "Re-ingested (dedup)"
    typer.echo(f"{verb}: {title}")


def main() -> None:
    """Console-script entry point."""
    app()

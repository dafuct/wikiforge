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

    from wikiforge.activity.cost import CostTracker
    from wikiforge.config.settings import load_config
    from wikiforge.embed.factory import build_embedding_provider, effective_embedding_dim
    from wikiforge.services import ingest_source
    from wikiforge.storage.db import Database
    from wikiforge.storage.repository import Repository

    target_home = resolve_home(home)

    async def _run() -> tuple[str, bool]:
        cfg = load_config(target_home)
        db = await Database.open(target_home, dim=effective_embedding_dim(cfg))
        try:
            repo = Repository(db)
            embedder = build_embedding_provider(cfg, repo, cost_tracker=CostTracker(repo, cfg))
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


ModeOption = typer.Option("standard", "--mode", help="Research breadth: standard, deep, or max.")
BudgetOption = typer.Option(
    None, "--budget", help="Stop starting new persona waves once session spend reaches this USD."
)


@app.command()
def research(
    topic: str = typer.Argument(..., help="Topic title to research."),
    home: str | None = HomeOption,
    mode: str = ModeOption,
    new_topic: bool = typer.Option(
        False, "--new-topic", help="Create the topic if it doesn't exist yet."
    ),
    budget: float | None = BudgetOption,
    resume: int | None = typer.Option(
        None, "--resume", help="Resume an existing research session by id."
    ),
) -> None:
    """Research a topic across persona agents, gathering and normalizing findings."""
    from wikiforge.services import run_research

    target_home = resolve_home(home)
    try:
        session = asyncio.run(
            run_research(
                target_home,
                topic,
                mode=mode,
                new_topic=new_topic,
                budget_usd=budget,
                resume_session_id=resume,
            )
        )
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(
        f"Research session #{session.id} ({session.status}) — spend ${session.spend_usd:.4f}"
    )


@app.command()
def thesis(
    claim: str = typer.Argument(..., help="The claim to evaluate."),
    home: str | None = HomeOption,
    mode: str = ModeOption,
    budget: float | None = BudgetOption,
) -> None:
    """Evaluate a thesis claim with FOR/AGAINST persona agents and a synthesized verdict."""
    from wikiforge.services import run_thesis

    target_home = resolve_home(home)
    try:
        verdict = asyncio.run(run_thesis(target_home, claim, mode=mode, budget_usd=budget))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Verdict: {verdict.verdict} (confidence {verdict.confidence:.2f})")
    typer.echo(verdict.rationale)


@app.command()
def compile(
    home: str | None = HomeOption,
    full: bool = typer.Option(
        False, "--full", help="Recompile every topic, ignoring the incremental digest."
    ),
) -> None:
    """Compile every active topic's gathered evidence into a synthesized, cited article."""
    from wikiforge.services import run_compile

    target_home = resolve_home(home)
    articles = asyncio.run(run_compile(target_home, full=full))
    if not articles:
        typer.echo("Nothing to compile.")
        return
    typer.echo(f"Compiled {len(articles)} article(s)")
    for article in articles:
        typer.echo(f"  {article.slug} (confidence {article.confidence:.2f})")


@app.command()
def related(
    topic: str = typer.Argument(..., help="Topic slug or title to look up."),
    home: str | None = HomeOption,
) -> None:
    """List topics related to a given topic via the knowledge graph."""
    from wikiforge.services import run_related

    target_home = resolve_home(home)
    try:
        pairs = asyncio.run(run_related(target_home, topic))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    if not pairs:
        typer.echo("No related topics found.")
        return
    for related_topic, score in pairs:
        typer.echo(f"{related_topic.slug}  {score:.4f}")


def main() -> None:
    """Console-script entry point."""
    app()

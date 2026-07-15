"""The `wiki` Typer application entry point."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path

import typer

from wikiforge.models.domain import Topic
from wikiforge.paths import resolve_home

app = typer.Typer(
    name="wiki",
    help="wikiforge — compile a personal knowledge base.",
    no_args_is_help=True,
)
dataset_app = typer.Typer(name="dataset", help="Manage tracked datasets.", no_args_is_help=True)
app.add_typer(dataset_app, name="dataset")

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
    from wikiforge.services import run_ingest

    target_home = resolve_home(home)
    source, created = asyncio.run(run_ingest(target_home, target))
    verb = "Ingested" if created else "Re-ingested (dedup)"
    typer.echo(f"{verb}: {source.title}")


@app.command()
def collect(
    collection_name: str = typer.Argument(..., help="Named collection to catalogue this item in."),
    target: str = typer.Argument(..., help="URL, PDF path, or text file to collect."),
    home: str | None = HomeOption,
) -> None:
    """Catalogue a URL/PDF/file into a named inventory collection (not indexed for search)."""
    from wikiforge.services import run_collect

    target_home = resolve_home(home)
    try:
        item = asyncio.run(run_collect(target_home, collection_name, target))
    except OSError as exc:
        typer.echo(f"Error: cannot read {target!r}: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Collected {item.name!r} ({item.kind}) into collection {item.collection_name!r}")


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
    from wikiforge.cli.live import LiveResearchTable
    from wikiforge.services import run_research

    target_home = resolve_home(home)
    reporter = LiveResearchTable()
    try:
        with reporter:
            session = asyncio.run(
                run_research(
                    target_home,
                    topic,
                    mode=mode,
                    new_topic=new_topic,
                    budget_usd=budget,
                    resume_session_id=resume,
                    reporter=reporter,
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
    try:
        articles = asyncio.run(run_compile(target_home, full=full))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
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


DepthOption = typer.Option(
    "standard", "--depth", help="Retrieval effort: quick, standard, or deep."
)


@app.command()
def query(
    question: str = typer.Argument(..., help="The question to ask the wiki."),
    home: str | None = HomeOption,
    depth: str = DepthOption,
    scope: str = typer.Option(
        "all", "--scope", help="What to search: all | articles | devlog."
    ),
    extract: bool = typer.Option(
        False,
        "--extract",
        help="Print matching excerpts with no LLM call (the caller synthesizes).",
    ),
) -> None:
    """Answer a question from the wiki's knowledge (articles + raw sources + dev log)."""
    from wikiforge.query.service import NO_RESULTS_ANSWER, render_excerpts
    from wikiforge.services import run_extract, run_query

    target_home = resolve_home(home)
    try:
        if extract:
            targets = asyncio.run(run_extract(target_home, question, depth=depth, scope=scope))
            typer.echo(render_excerpts(targets) if targets else NO_RESULTS_ANSWER)
            return
        result = asyncio.run(run_query(target_home, question, depth=depth, scope=scope))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(result.answer)
    if result.sources:
        typer.echo("\nSources:")
        for source in result.sources:
            typer.echo(f"  {source.owner_type}:{source.owner_id}#{source.seq}")


@app.command()
def generate(
    kind: str = typer.Argument(
        ...,
        help="report | slides-outline | summary | study-guide | timeline | glossary | comparison.",
    ),
    topic: str = typer.Argument(..., help="Topic slug or title to generate from."),
    home: str | None = HomeOption,
    out: str | None = typer.Option(None, "--out", help="Write the output to this file path."),
) -> None:
    """Generate a derived document from a topic's compiled article."""
    from wikiforge.services import run_generate

    out_path = Path(out) if out is not None else None
    try:
        text = asyncio.run(run_generate(resolve_home(home), kind, topic, out=out_path))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    if out_path is not None:
        typer.echo(f"Wrote {kind} for {topic!r} to {out_path}")
    else:
        typer.echo(text)


@app.command()
def lint(
    home: str | None = HomeOption,
    fix: bool = typer.Option(
        False, "--fix", help="Apply safe auto-repairs (currently: strip broken wikilinks)."
    ),
) -> None:
    """Audit the wiki for broken links, orphaned articles, missing citations, and staleness."""
    from wikiforge.services import run_lint

    target_home = resolve_home(home)
    findings, fixed = asyncio.run(run_lint(target_home, fix=fix))
    if not findings:
        typer.echo("No issues found.")
        return
    for finding in findings:
        typer.echo(f"{finding.kind}  {finding.topic_slug}  {finding.detail}")
    typer.echo(f"\n{len(findings)} issue(s) found")
    if fix:
        typer.echo(f"Fixed {fixed} of them")


@app.command()
def audit(
    topic: str = typer.Argument(..., help="Topic slug to audit for citation drift."),
    home: str | None = HomeOption,
) -> None:
    """Re-verify a topic's citations still match their (immutable) raw sources."""
    from wikiforge.services import run_audit

    target_home = resolve_home(home)
    try:
        findings = asyncio.run(run_audit(target_home, topic))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    if not findings:
        typer.echo("No citation drift found.")
        return
    for finding in findings:
        typer.echo(f"{finding.claim} -> source {finding.raw_source_id}: {finding.issue}")
    typer.echo(f"\n{len(findings)} issue(s) found")


@app.command()
def feedback(
    target: str = typer.Argument(
        ..., help="Feedback target: article:<id> or finding:<id> (bare id defaults to article)."
    ),
    action: str = typer.Argument(..., help="Verdict: approve, reject, or correct."),
    note: str = typer.Argument("", help="Free-text note explaining the verdict."),
    home: str | None = HomeOption,
) -> None:
    """Record a feedback verdict against a compiled article or research finding."""
    from wikiforge.services import run_feedback

    target_home = resolve_home(home)
    try:
        feedback_id = asyncio.run(run_feedback(target_home, target, action, note))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Recorded feedback #{feedback_id} ({action}) on {target}")


@app.command()
def archive(
    topic: str = typer.Argument(..., help="Topic slug to archive."),
    home: str | None = HomeOption,
) -> None:
    """Archive a topic, excluding it from the default query/retrieval scope."""
    from wikiforge.services import run_archive

    target_home = resolve_home(home)
    try:
        result = asyncio.run(run_archive(target_home, topic))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Archived topic {result.slug!r} ({result.title})")


@dataset_app.command("add")
def dataset_add(
    name: str = typer.Argument(..., help="Dataset name."),
    path: str = typer.Argument(..., help="Path to the dataset file."),
    home: str | None = HomeOption,
) -> None:
    """Record an on-disk dataset's name, path, and byte size."""
    from wikiforge.services import run_dataset_add

    target_home = resolve_home(home)
    try:
        dataset = asyncio.run(run_dataset_add(target_home, name, Path(path)))
    except OSError as exc:
        typer.echo(f"Error: cannot read {path!r}: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Added dataset {dataset.name!r}: {dataset.path} ({dataset.bytes} bytes)")


def _overdue_text(topic: Topic) -> str:
    """Describe how overdue a stale ``Topic`` is, for the ``refresh`` listing."""
    if topic.last_researched_at is None:
        return "never researched"
    last = topic.last_researched_at
    last = last if last.tzinfo is not None else last.replace(tzinfo=UTC)
    age_days = (datetime.now(UTC) - last).days
    return f"last researched {age_days}d ago (stale after {topic.stale_after_days}d)"


@app.command()
def refresh(
    home: str | None = HomeOption,
    run: bool = typer.Option(
        False, "--run", help="Re-research each stale topic instead of only listing it."
    ),
) -> None:
    """List topics whose freshness window has lapsed; with --run, re-research them."""
    from wikiforge.services import run_refresh

    target_home = resolve_home(home)
    try:
        topics = asyncio.run(run_refresh(target_home, run=run))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    if not topics:
        typer.echo("All topics are fresh.")
        return
    if run:
        slugs = ", ".join(t.slug for t in topics)
        typer.echo(f"Re-researched {len(topics)} stale topic(s): {slugs}")
    else:
        typer.echo(f"{len(topics)} stale topic(s):")
        for topic in topics:
            typer.echo(f"  {topic.slug} — {_overdue_text(topic)}")


@app.command()
def stats(
    home: str | None = HomeOption,
    since: str | None = typer.Option(
        None, "--since", help="Only count LLM calls/cost at or after this date (YYYY-MM-DD)."
    ),
) -> None:
    """Show wiki size (topics/articles/sources/sessions) and LLM spend."""
    from wikiforge.services import run_stats

    s = asyncio.run(run_stats(resolve_home(home), since=since))
    typer.echo(f"Topics: {s.topics}   Articles: {s.articles}")
    typer.echo(f"Raw sources: {s.raw_sources}   Research sessions: {s.sessions}")
    typer.echo(f"Total LLM spend: ${s.total_cost_usd:.4f}")
    for model, cost in sorted(s.cost_by_model.items()):
        typer.echo(f"  {model}: ${cost:.4f}")
    if s.since is not None:
        typer.echo(f"Since {s.since}: {s.calls_since} call(s), ${s.cost_since_usd:.4f}")


@app.command()
def context(home: str | None = HomeOption) -> None:
    """Print a recent-activity digest suitable for pasting into an agent's context."""
    from wikiforge.services import run_context

    typer.echo(asyncio.run(run_context(resolve_home(home))))


@app.command()
def export(
    target: str = typer.Argument(..., help="obsidian | site | json."),
    home: str | None = HomeOption,
    out: str | None = typer.Option(
        None, "--out", help="Output directory (default: <home>/export/<target>)."
    ),
) -> None:
    """Export the wiki to an Obsidian vault, a static site, or a JSON dump."""
    from wikiforge.services import run_export

    out_path = Path(out) if out is not None else None
    try:
        written = asyncio.run(run_export(resolve_home(home), target, out_path))
    except ValueError as exc:
        typer.echo(f"Error: {exc}", err=True)
        raise typer.Exit(code=1) from None
    typer.echo(f"Exported {target} to {written}")


@app.command(name="serve-mcp")
def serve_mcp(home: str | None = HomeOption) -> None:
    """Serve the wiki over the Model Context Protocol (stdio transport)."""
    from wikiforge.mcp.server import build_server

    build_server(resolve_home(home)).run(transport="stdio")


@app.command()
def capture(
    home: str | None = HomeOption,
    hook: bool = typer.Option(False, "--hook", help="Read Claude Code Stop-hook JSON from stdin."),
    note: str | None = typer.Option(None, "--note", help="Manually capture this request/decision."),
    type_: str | None = typer.Option(
        None, "--type", help="Event type label (feature/bugfix/research/design/...)."
    ),
    flush: bool = typer.Option(
        False, "--flush",
        help="Backfill dev-log vectors (free); with --digests also batch-summarize pending events.",
    ),
    digests: bool = typer.Option(
        False, "--digests", help="With --flush: one cheap LLM call per batch of pending events."
    ),
) -> None:
    """Record a development event: auto from a Stop hook (--hook), or a manual --note."""
    if flush:
        from wikiforge.paths import resolve_capture_home
        from wikiforge.services import run_capture_flush

        target_home = resolve_capture_home(home)
        stats = asyncio.run(run_capture_flush(target_home, digests=digests))
        typer.echo(
            f"flush: {stats.embedded_chunks} chunks embedded, "
            f"{stats.digested_events} events digested, {stats.pending_left} pending"
        )
        return

    if hook:
        try:
            import sys

            from wikiforge.paths import resolve_capture_home
            from wikiforge.services import run_capture_hook

            target_home = resolve_capture_home(home)
            stdin = sys.stdin.read() if not sys.stdin.isatty() else ""
            asyncio.run(run_capture_hook(target_home, stdin))
        except Exception:
            pass  # a Stop hook must never break the session
        return

    from wikiforge.paths import resolve_capture_home

    target_home = resolve_capture_home(home)
    if note is None:
        typer.echo("Error: provide --note TEXT or --hook", err=True)
        raise typer.Exit(code=1) from None
    from wikiforge.services import run_capture_note

    source = asyncio.run(run_capture_note(target_home, note, event_type=type_))
    if source is None:
        typer.echo("No wiki initialized here; nothing captured.")
        return
    typer.echo(f"Captured dev event: {source.title}")


def main() -> None:
    """Console-script entry point."""
    app()

"""The shared service layer. Both the CLI and the MCP server call these functions.

Milestone 1 provides ``init_wiki``; Milestone 2 adds ``ingest_source`` and
``detect_target_kind``. Later milestones extend this module further.
"""

from __future__ import annotations

import re
from pathlib import Path

import httpx

from wikiforge.activity.recorder import ActivityRecorder
from wikiforge.activity.stats import StatsService, WikiStats
from wikiforge.config.settings import (
    CONFIG_FILENAME,
    load_config,
    write_default_config,
)
from wikiforge.embed.factory import effective_embedding_dim
from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.ingest import sources as ingest_sources
from wikiforge.lint.auditor import AuditFinding, WikiAuditor
from wikiforge.lint.linter import LintFinding, WikiLinter
from wikiforge.models.domain import (
    Article,
    Dataset,
    InventoryItem,
    RawSource,
    ResearchSession,
    ThesisVerdict,
    Topic,
)
from wikiforge.models.enums import OutputKind, QueryDepth
from wikiforge.output.generator import OutputGenerator
from wikiforge.query.service import QueryResult
from wikiforge.search.index import index_owner
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def init_wiki(name: str, home: Path) -> Path:
    """Scaffold a wiki home: config, database, topics dir, and an init log row.

    Idempotent: an existing ``config.toml`` is left untouched; the schema is
    created with ``IF NOT EXISTS`` DDL.
    """
    home.mkdir(parents=True, exist_ok=True)
    (home / "topics").mkdir(exist_ok=True)
    if not (home / CONFIG_FILENAME).exists():
        write_default_config(home, wiki_name=name)
    cfg = load_config(home)

    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        await db.init_schema()
        repo = Repository(db)
        await repo.set_meta("embedding_dim", str(effective_embedding_dim(cfg)))
        recorder = ActivityRecorder(repo)
        await recorder.record("init", {"name": name}, summary=f"created wiki {name!r}")
    finally:
        await db.close()
    return home


def detect_target_kind(target: str) -> str:
    """Classify an ingest target as ``url``, ``pdf``, or ``file``."""
    if target.startswith(("http://", "https://")):
        return "url"
    if target.lower().endswith(".pdf"):
        return "pdf"
    return "file"


async def build_raw_source(target: str, *, http_client: httpx.AsyncClient) -> RawSource:
    """Classify ``target`` and build its (not-yet-persisted) ``RawSource`` via the M2 adapters.

    Shared by :func:`ingest_source` and :func:`wikiforge.ops.inventory.collect` so both
    entry points use identical URL/PDF/file classification and extraction.
    """
    kind = detect_target_kind(target)
    if kind == "url":
        return await ingest_sources.ingest_url(target, client=http_client)
    if kind == "pdf":
        return ingest_sources.ingest_pdf(Path(target))
    return ingest_sources.ingest_file(Path(target))


async def ingest_source(
    home: Path,
    target: str,
    *,
    http_client: httpx.AsyncClient,
    embedder: EmbeddingProvider,
    _db: Database | None = None,
) -> tuple[RawSource, bool]:
    """Ingest a URL/PDF/file/text target into an immutable, indexed raw source.

    Builds a ``RawSource``, dedups it by content hash (immutable text; provenance
    refreshed on re-ingest), indexes it into chunks/FTS/vector, and records an
    ``ingest`` activity row. Returns ``(stored_source, created)``.

    ``_db`` lets a caller pass an already-open ``Database``: the CLI does this
    to share one connection/lock with a caller-built ``Repository``, and tests
    do it so they can assert on the DB afterward. When omitted, one is opened
    from ``home`` and closed on exit.
    """
    kind = detect_target_kind(target)
    source = await build_raw_source(target, http_client=http_client)

    db = _db or await Database.open(home, dim=embedder.dim)
    try:
        repo = Repository(db)
        source_id, created = await repo.ingest_raw_source(source)
        stored = await repo.get_raw_source_by_hash(source.content_hash)
        if stored is None:
            raise RuntimeError("stored raw source missing after ingest")
        expected_dim = await repo.get_meta("embedding_dim")
        if expected_dim is not None and int(expected_dim) != embedder.dim:
            raise ValueError(
                f"this wiki was initialized for embedding dimension {expected_dim}, but "
                f"the active embedder produces {embedder.dim}. Set or unset VOYAGE_API_KEY "
                "to match the init-time provider, or re-init the wiki."
            )
        await index_owner(
            repo, embedder, owner_type="raw_source", owner_id=source_id, text=stored.text
        )
        recorder = ActivityRecorder(repo)
        await recorder.record(
            "ingest",
            {"target": target, "kind": kind},
            summary=f"{'ingested' if created else 're-ingested'} {source.title!r}",
        )
        return stored, created
    finally:
        if _db is None:
            await db.close()


def slugify(text: str) -> str:
    """Return a URL/filesystem-safe slug: lowercase, non-alphanumerics collapsed to hyphens."""
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")


async def _resolve_topic(repo: Repository, ref: str) -> Topic:
    """Resolve a topic by slug, falling back to a case-insensitive title match.

    Raises ``ValueError`` when no topic matches ``ref``.
    """
    topic = await repo.get_topic(ref)
    if topic is not None:
        return topic
    wanted = ref.strip().lower()
    for candidate in await repo.list_topics():
        if candidate.title.strip().lower() == wanted:
            return candidate
    raise ValueError(f"unknown topic {ref!r}")


async def run_research(
    home: Path,
    topic_text: str,
    *,
    mode: str,
    new_topic: bool,
    budget_usd: float | None,
    resume_session_id: int | None,
) -> ResearchSession:
    """Run (or resume) a research session for a topic.

    Resolves the topic by slug. If it doesn't exist yet, it is created only
    when ``new_topic`` is set (with volatility inferred via
    :func:`~wikiforge.research.volatility.infer_volatility`); otherwise a
    ``ValueError`` is raised. Delegates the actual persona fan-out to
    :class:`~wikiforge.research.orchestrator.ResearchOrchestrator`.
    """
    from anthropic import AsyncAnthropic

    from wikiforge.activity.cost import CostTracker
    from wikiforge.llm.anthropic_provider import AnthropicProvider
    from wikiforge.research.orchestrator import ResearchOrchestrator
    from wikiforge.research.volatility import infer_volatility

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        llm = AnthropicProvider(AsyncAnthropic(), CostTracker(repo, cfg), cfg)
        slug = slugify(topic_text)
        topic = await repo.get_topic(slug)
        if topic is None:
            if not new_topic:
                raise ValueError(f"unknown topic {topic_text!r}; pass --new-topic to create it")
            volatility, stale = await infer_volatility(llm, topic_text, cfg)
            topic_id = await repo.upsert_topic(
                Topic(slug=slug, title=topic_text, volatility=volatility, stale_after_days=stale)
            )
        else:
            if topic.id is None:
                raise RuntimeError(f"topic {slug!r} has no id")
            topic_id = topic.id
        orch = ResearchOrchestrator(llm, repo, cfg)
        return await orch.research(
            topic_id=topic_id,
            topic_title=topic_text,
            mode=mode,
            budget_usd=budget_usd,
            resume_session_id=resume_session_id,
        )
    finally:
        await db.close()


async def run_thesis(
    home: Path,
    claim: str,
    *,
    mode: str,
    budget_usd: float | None,
) -> ThesisVerdict:
    """Evaluate a thesis claim via FOR/AGAINST persona agents.

    Delegates fan-out and verdict synthesis to
    :meth:`~wikiforge.research.orchestrator.ResearchOrchestrator.evaluate_thesis`.
    """
    from anthropic import AsyncAnthropic

    from wikiforge.activity.cost import CostTracker
    from wikiforge.llm.anthropic_provider import AnthropicProvider
    from wikiforge.research.orchestrator import ResearchOrchestrator

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        llm = AnthropicProvider(AsyncAnthropic(), CostTracker(repo, cfg), cfg)
        orch = ResearchOrchestrator(llm, repo, cfg)
        return await orch.evaluate_thesis(claim=claim, mode=mode, budget_usd=budget_usd)
    finally:
        await db.close()


async def run_compile(home: Path, *, full: bool) -> list[Article]:
    """Compile every active topic's gathered evidence into a synthesized, cited article.

    Builds the real LLM provider and the factory embedding provider (Voyage if
    keyed, else the local model), then delegates to
    :meth:`~wikiforge.compile.compiler.Compiler.compile_all`. Returns an empty
    list when there is nothing to compile (no topics, or every topic's digest
    is already up to date and ``full`` is not set).
    """
    from anthropic import AsyncAnthropic

    from wikiforge.activity.cost import CostTracker
    from wikiforge.compile.compiler import Compiler
    from wikiforge.embed.factory import build_embedding_provider
    from wikiforge.llm.anthropic_provider import AnthropicProvider

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        tracker = CostTracker(repo, cfg)
        llm = AnthropicProvider(AsyncAnthropic(), tracker, cfg)
        embedder = build_embedding_provider(cfg, repo, cost_tracker=tracker)
        compiler = Compiler(llm, embedder, repo, cfg, home)
        return await compiler.compile_all(force=full)
    finally:
        await db.close()


async def run_related(home: Path, topic_text: str) -> list[tuple[Topic, float]]:
    """Return a topic's knowledge-graph neighbours, most similar first.

    Resolves the topic by slug and raises ``ValueError`` if it is unknown.
    Reads the similarity links stored by the last compile
    (:func:`~wikiforge.graph.links.refresh_topic_links`); it does not need an
    LLM or embedding provider of its own.
    """
    from wikiforge.graph.links import related_topics

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        slug = slugify(topic_text)
        topic = await repo.get_topic(slug)
        if topic is None:
            raise ValueError(f"unknown topic {topic_text!r}; topic not found")
        if topic.id is None:
            raise RuntimeError(f"topic {slug!r} has no id")
        return await related_topics(repo, topic.id)
    finally:
        await db.close()


async def run_query(home: Path, query: str, *, depth: str) -> QueryResult:
    """Answer a question against the wiki, citing the retrieved chunks it relied on.

    Assembles the real ``AnthropicProvider``, the factory-selected embedding provider,
    and a ``HybridRetriever``, then delegates to
    :func:`~wikiforge.query.service.answer_query`. For ``depth="deep"`` a real
    sentence-transformers ``CrossEncoder`` (``retrieval.rerank_model``) is lazily built
    and wired in as the reranker; ``quick``/``standard`` queries never load it.
    """
    from anthropic import AsyncAnthropic

    from wikiforge.activity.cost import CostTracker
    from wikiforge.embed.factory import build_embedding_provider
    from wikiforge.llm.anthropic_provider import AnthropicProvider
    from wikiforge.query.service import answer_query
    from wikiforge.search.retriever import HybridRetriever, Reranker

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        tracker = CostTracker(repo, cfg)
        llm = AnthropicProvider(AsyncAnthropic(), tracker, cfg)
        embedder = build_embedding_provider(cfg, repo, cost_tracker=tracker)

        reranker: Reranker | None = None
        if depth == QueryDepth.DEEP:
            from sentence_transformers import CrossEncoder

            cross_encoder = CrossEncoder(cfg.retrieval.rerank_model)

            def _rerank(q: str, docs: list[str]) -> list[float]:
                scores = cross_encoder.predict([(q, doc) for doc in docs])
                return [float(s) for s in scores]

            reranker = _rerank

        retriever = HybridRetriever(repo, embedder, cfg, reranker=reranker)
        return await answer_query(llm, retriever, query, depth=depth)
    finally:
        await db.close()


async def run_generate(home: Path, kind: str, topic: str, *, out: Path | None) -> str:
    """Generate a derived document (report/summary/...) for a topic's latest article.

    ``kind`` must be an :class:`~wikiforge.models.enums.OutputKind` value. Resolves
    the topic (slug or title), loads its latest compiled article, and runs the
    flagship :class:`~wikiforge.output.generator.OutputGenerator`. Writes the text to
    ``out`` when given; always returns it. Raises ``ValueError`` for an unknown
    topic, an invalid kind, or a topic with no compiled article.
    """
    from anthropic import AsyncAnthropic

    from wikiforge.activity.cost import CostTracker
    from wikiforge.llm.anthropic_provider import AnthropicProvider

    output_kind = OutputKind(kind)  # raises ValueError on a bad kind
    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        resolved = await _resolve_topic(repo, topic)
        assert resolved.id is not None
        article = await repo.latest_article_for_topic(resolved.id)
        if article is None:
            raise ValueError(f"topic {resolved.slug!r} has no compiled article; run `wiki compile`")
        llm = AnthropicProvider(AsyncAnthropic(), CostTracker(repo, cfg), cfg)
        text = await OutputGenerator(llm).generate(
            output_kind, topic_title=resolved.title, article_body=article.body_md
        )
    finally:
        await db.close()
    if out is not None:
        out.write_text(text, encoding="utf-8")
    return text


async def run_lint(home: Path, *, fix: bool) -> tuple[list[LintFinding], int]:
    """Audit the wiki for broken links, orphans, missing citations, and staleness.

    Builds a :class:`~wikiforge.lint.linter.WikiLinter` bound to ``home`` (so a
    ``--fix`` pass can rewrite on-disk Markdown, not just the DB row), runs
    :meth:`~wikiforge.lint.linter.WikiLinter.lint`, and — when ``fix`` is set —
    immediately applies :meth:`~wikiforge.lint.linter.WikiLinter.fix` to every
    finding it just found. Returns ``(findings, fixed)`` where ``findings`` is what
    the lint pass reported (whether or not repaired) and ``fixed`` is the count
    :meth:`~wikiforge.lint.linter.WikiLinter.fix` actually repaired (0 without
    ``fix``) — the linter may safely skip a finding whose markup is already gone.
    """
    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        linter = WikiLinter(repo, home=home)
        findings = await linter.lint()
        fixed = await linter.fix(findings) if fix else 0
        return findings, fixed
    finally:
        await db.close()


def _parse_feedback_target(target: str) -> tuple[str, int]:
    """Parse a ``<type>:<id>`` feedback target, defaulting to ``article`` for a bare id."""
    if ":" in target:
        kind, _, raw_id = target.partition(":")
        return kind, int(raw_id)
    return "article", int(target)


async def run_feedback(home: Path, target: str, action: str, note: str) -> int:
    """Record a feedback verdict against an article or finding target.

    ``target`` is ``article:<id>`` or ``finding:<id>``; a bare integer defaults
    to ``article:<id>``. ``action`` is ``approve``, ``reject``, or ``correct``,
    mapped to :class:`~wikiforge.models.enums.FeedbackVerdict`. Returns the new
    feedback row's id.
    """
    from wikiforge.models.enums import FeedbackVerdict
    from wikiforge.ops.feedback import FeedbackStore

    target_type, target_id = _parse_feedback_target(target)
    verdict = FeedbackVerdict(action)

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        store = FeedbackStore(repo)
        return await store.record(target_type, target_id, verdict, note)
    finally:
        await db.close()


async def run_refresh(home: Path, *, run: bool) -> list[Topic]:
    """List (or, when ``run``, re-research) topics whose freshness window has lapsed.

    Builds the real ``AnthropicProvider``/``ResearchOrchestrator`` only when
    ``run`` is set — a plain listing needs no network access, so ``--run``-less
    calls never construct one.
    """
    from datetime import UTC, datetime

    from wikiforge.ops.freshness import refresh_topics, stale_topics

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        now = datetime.now(UTC)
        if not run:
            return await stale_topics(repo, now=now)

        from anthropic import AsyncAnthropic

        from wikiforge.activity.cost import CostTracker
        from wikiforge.llm.anthropic_provider import AnthropicProvider
        from wikiforge.research.orchestrator import ResearchOrchestrator

        llm = AnthropicProvider(AsyncAnthropic(), CostTracker(repo, cfg), cfg)
        orch = ResearchOrchestrator(llm, repo, cfg)
        return await refresh_topics(orch, repo, now=now, run=True)
    finally:
        await db.close()


async def run_audit(home: Path, slug: str) -> list[AuditFinding]:
    """Re-verify a topic's citation quotes against their immutable raw sources.

    Resolves the topic by slug and delegates to
    :meth:`~wikiforge.lint.auditor.WikiAuditor.audit_topic`, which raises
    ``ValueError`` for an unknown slug. Returns an empty list when no citation
    drift is found.
    """
    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        auditor = WikiAuditor(repo)
        return await auditor.audit_topic(slug)
    finally:
        await db.close()


async def run_collect(home: Path, collection_name: str, target: str) -> InventoryItem:
    """Ingest ``target`` into a named inventory collection.

    Builds a real ``httpx.AsyncClient`` and delegates to
    :func:`wikiforge.ops.inventory.collect`, which reuses the same M2 classification
    and adapters as :func:`ingest_source` but only catalogues the result (no chunk
    indexing), keeping collected items out of the default query search scope.
    """
    from wikiforge.ops.inventory import collect

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        async with httpx.AsyncClient() as client:
            return await collect(repo, collection_name, target, http_client=client)
    finally:
        await db.close()


async def run_dataset_add(home: Path, name: str, path: Path) -> Dataset:
    """Record an on-disk dataset's name, path, and byte size.

    Delegates to :func:`wikiforge.ops.inventory.add_dataset`.
    """
    from wikiforge.ops.inventory import add_dataset

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        return await add_dataset(repo, name, path)
    finally:
        await db.close()


async def run_archive(home: Path, slug: str) -> Topic:
    """Archive a topic by slug, excluding it from the default query/retrieval scope.

    Delegates to :func:`wikiforge.ops.inventory.archive_topic`, which raises
    ``ValueError`` for an unknown slug.
    """
    from wikiforge.ops.inventory import archive_topic

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        return await archive_topic(repo, slug)
    finally:
        await db.close()


async def run_stats(home: Path, *, since: str | None) -> WikiStats:
    """Compute a wiki-wide stats snapshot (counts + cost totals, optional since window)."""
    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        return await StatsService(Repository(db)).compute(since=since)
    finally:
        await db.close()


async def run_context(home: Path, *, limit: int = 20) -> str:
    """Render the recent-activity digest (the `wiki context` CLAUDE.md-style summary)."""
    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        return await ActivityRecorder(Repository(db)).context_digest(limit)
    finally:
        await db.close()

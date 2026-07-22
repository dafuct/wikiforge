"""The shared service layer. Both the CLI and the MCP server call these functions.

Milestone 1 provides ``init_wiki``; Milestone 2 adds ``ingest_source`` and
``detect_target_kind``. Later milestones extend this module further.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import httpx

from wikiforge.activity.recorder import ActivityRecorder
from wikiforge.activity.stats import StatsService, WikiStats
from wikiforge.config.settings import (
    CONFIG_FILENAME,
    Config,
    load_config,
    write_default_config,
)
from wikiforge.embed.factory import build_embedding_provider, effective_embedding_dim
from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.federation.peers import PeerStatus
from wikiforge.federation.registry import PeerRef
from wikiforge.ingest import sources as ingest_sources
from wikiforge.lint.auditor import WikiAuditor
from wikiforge.lint.linter import LintFinding, WikiLinter
from wikiforge.llm.factory import build_llm_provider
from wikiforge.models.domain import (
    Article,
    Dataset,
    InventoryItem,
    RawSource,
    ResearchSession,
    ThesisVerdict,
    Topic,
)
from wikiforge.models.enums import ExportTarget, OutputKind, QueryDepth
from wikiforge.ops.flush import FlushStats
from wikiforge.ops.maintain import MaintainReport
from wikiforge.ops.scope import events_for_absolute, events_for_paths, repo_root
from wikiforge.output.exporter import Exporter
from wikiforge.output.generator import OutputGenerator
from wikiforge.query.service import QueryResult
from wikiforge.research.progress import ResearchReporter
from wikiforge.search.index import index_owner
from wikiforge.search.rrf import ChunkTarget
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

if TYPE_CHECKING:
    from wikiforge.federation.fanout import Sourced
    from wikiforge.ops.consolidate import ConsolidateStats
    from wikiforge.ops.impact import AuditResult
    from wikiforge.search.retriever import Reranker


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


async def ensure_embedding_compat(repo: Repository, embedder: EmbeddingProvider) -> None:
    """Stamp or verify the wiki's embedding model; mismatch demands a reindex.

    The first caller records ``embedding_model`` in wiki meta. Afterwards a
    different active model raises instead of silently fusing incompatible
    vectors with FTS results.
    """
    stored = await repo.get_meta("embedding_model")
    if stored is None:
        await repo.set_meta("embedding_model", embedder.model)
        return
    if stored != embedder.model:
        raise ValueError(
            f"this wiki's chunk vectors were built with embedding model {stored!r}, but the "
            f"active model is {embedder.model!r}; run `wiki reindex --embeddings` to rebuild."
        )


async def run_reindex(home: Path) -> int:
    """Rebuild every chunk vector with the active embedding provider (zero LLM).

    Recreates the vec0 table at the active dimension, re-embeds all chunks in
    batches of 500, restamps the meta keys, and purges stale embedding-cache
    rows. Returns the number of chunks embedded.
    """
    from wikiforge.activity.cost import CostTracker

    cfg = load_config(home)
    dim = effective_embedding_dim(cfg)
    db = await Database.open(home, dim=dim)
    try:
        repo = Repository(db)
        embedder = build_embedding_provider(cfg, repo, cost_tracker=CostTracker(repo, cfg))
        await db.recreate_vec_table()
        embedded = 0
        while True:
            rows = await repo.all_chunks_missing_vectors(limit=500)
            if not rows:
                break
            vectors = await embedder.embed([text for _, text in rows])
            for (rowid, _), vector in zip(rows, vectors, strict=True):
                await repo.insert_chunk_vector(rowid, vector)
            embedded += len(rows)
        await repo.set_meta("embedding_model", embedder.model)
        await repo.set_meta("embedding_dim", str(dim))
        await repo.purge_embedding_cache(embedder.model)
        recorder = ActivityRecorder(repo)
        await recorder.record("reindex", {}, summary=f"re-embedded {embedded} chunks")
        return embedded
    finally:
        await db.close()


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
        await ensure_embedding_compat(repo, embedder)
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


async def run_ingest(home: Path, target: str) -> tuple[RawSource, bool]:
    """Ingest a URL/PDF/file target into the wiki, returning (source, created).

    Builds the real embedder + HTTP client and delegates to :func:`ingest_source`.
    """
    from wikiforge.activity.cost import CostTracker

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        embedder = build_embedding_provider(cfg, repo, cost_tracker=CostTracker(repo, cfg))
        async with httpx.AsyncClient() as client:
            return await ingest_source(home, target, http_client=client, embedder=embedder, _db=db)
    finally:
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
    reporter: ResearchReporter | None = None,
) -> ResearchSession:
    """Run (or resume) a research session for a topic.

    Resolves the topic by slug. If it doesn't exist yet, it is created only
    when ``new_topic`` is set (with volatility inferred via
    :func:`~wikiforge.research.volatility.infer_volatility`); otherwise a
    ``ValueError`` is raised. Delegates the actual persona fan-out to
    :class:`~wikiforge.research.orchestrator.ResearchOrchestrator`. ``reporter``
    is forwarded to the orchestrator for live progress (default: no-op).
    """
    from wikiforge.activity.cost import CostTracker
    from wikiforge.research.orchestrator import ResearchOrchestrator
    from wikiforge.research.volatility import infer_volatility

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        llm = build_llm_provider(cfg, CostTracker(repo, cfg))
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
            reporter=reporter,
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
    from wikiforge.activity.cost import CostTracker
    from wikiforge.research.orchestrator import ResearchOrchestrator

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        llm = build_llm_provider(cfg, CostTracker(repo, cfg))
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
    from wikiforge.activity.cost import CostTracker
    from wikiforge.compile.compiler import Compiler

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        tracker = CostTracker(repo, cfg)
        llm = build_llm_provider(cfg, tracker)
        embedder = build_embedding_provider(cfg, repo, cost_tracker=tracker)
        await ensure_embedding_compat(repo, embedder)
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


def _reranker_for(cfg: Config, depth: str) -> Reranker | None:
    """Lazily build the deep-depth cross-encoder reranker; ``None`` otherwise."""
    if depth != QueryDepth.DEEP:
        return None
    from sentence_transformers import CrossEncoder

    cross_encoder = CrossEncoder(cfg.retrieval.rerank_model)

    def _rerank(q: str, docs: list[str]) -> list[float]:
        scores = cross_encoder.predict([(q, doc) for doc in docs])
        return [float(s) for s in scores]

    return _rerank


async def run_query(home: Path, query: str, *, depth: str, scope: str = "all") -> QueryResult:
    """Answer a question against the wiki, citing the retrieved chunks it relied on.

    Assembles the factory-selected LLM provider, the factory-selected embedding provider,
    and a ``HybridRetriever``, then delegates to
    :func:`~wikiforge.query.service.answer_query`. For ``depth="deep"`` a real
    sentence-transformers ``CrossEncoder`` (``retrieval.rerank_model``) is lazily built
    and wired in as the reranker; ``quick``/``standard`` queries never load it.
    """
    from wikiforge.activity.cost import CostTracker
    from wikiforge.query.service import answer_query
    from wikiforge.search.retriever import HybridRetriever

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        tracker = CostTracker(repo, cfg)
        llm = build_llm_provider(cfg, tracker)
        embedder = build_embedding_provider(cfg, repo, cost_tracker=tracker)
        await ensure_embedding_compat(repo, embedder)
        retriever = HybridRetriever(repo, embedder, cfg, reranker=_reranker_for(cfg, depth))
        return await answer_query(llm, retriever, query, depth=depth, scope=scope)
    finally:
        await db.close()


async def run_extract(
    home: Path, query: str, *, depth: str, scope: str = "all"
) -> list[Sourced[ChunkTarget]]:
    """Retrieve cited excerpts with NO LLM provider constructed (zero-LLM read path).

    Builds only the embedder + retriever — never :func:`~wikiforge.llm.factory.build_llm_provider`
    — then delegates to :func:`~wikiforge.query.service.extract_query`. Intended for a
    calling agent whose context is already paid for, so it can synthesize the answer
    itself instead of paying for a second LLM round trip.

    Federated (cycle 4): the query is embedded once here and that SAME vector is
    reused both for the local retrieval and for every compatible peer's vector
    search — sound only because a peer's contribution is gated on its stamped
    ``embedding_model`` matching this wiki's active one (see ``extract_query``'s
    ``require_compat`` fan-out). Reuses the embedder already built above; a second
    embedding provider is never constructed.
    """
    from wikiforge.federation.fanout import active_peers
    from wikiforge.query.service import extract_query
    from wikiforge.search.retriever import HybridRetriever

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        embedder = build_embedding_provider(cfg, repo)
        await ensure_embedding_compat(repo, embedder)
        retriever = HybridRetriever(repo, embedder, cfg, reranker=_reranker_for(cfg, depth))
        (query_vec,) = await embedder.embed([query], kind="query")
        return await extract_query(
            retriever,
            query,
            depth=depth,
            scope=scope,
            peers=active_peers(cfg),
            dim=effective_embedding_dim(cfg),
            cfg=cfg,
            query_vec=query_vec,
            local_model=embedder.model,
        )
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
    from wikiforge.activity.cost import CostTracker

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
        llm = build_llm_provider(cfg, CostTracker(repo, cfg))
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

    Builds the factory-selected LLM provider and ``ResearchOrchestrator`` only when
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

        from wikiforge.activity.cost import CostTracker
        from wikiforge.research.orchestrator import ResearchOrchestrator

        llm = build_llm_provider(cfg, CostTracker(repo, cfg))
        orch = ResearchOrchestrator(llm, repo, cfg)
        return await refresh_topics(orch, repo, now=now, run=True)
    finally:
        await db.close()


async def run_audit(home: Path, slug: str, *, impact: bool = True) -> AuditResult:
    """Re-verify a topic's citation quotes, and show what else rests on drifted sources.

    The drift check is pure string comparison — zero LLM — so chaining into the
    blast radius costs nothing. One impact report per *distinct* drifted source,
    not per finding. ``impact=False`` restores the pre-chaining output.
    """
    from wikiforge.ops.impact import AuditResult, build_source_impact

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        findings = await WikiAuditor(repo).audit_topic(slug)
        if not impact or not findings:
            return AuditResult(findings=findings, impacts=[])
        impacts = []
        for source_id in dict.fromkeys(f.raw_source_id for f in findings):
            source = await repo.get_raw_source_by_id(source_id)
            if source is not None:
                impacts.append(await build_source_impact(repo, source, limit=20))
        return AuditResult(findings=findings, impacts=impacts)
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


async def run_export(home: Path, target: str, out: Path | None) -> Path:
    """Export the wiki to obsidian/site/json. Defaults ``out`` to ``home/export/<target>``.

    Raises ``ValueError`` for an invalid target.
    """
    export_target = ExportTarget(target)  # raises ValueError on a bad target
    destination = out if out is not None else home / "export" / target
    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        exporter = Exporter(Repository(db), wiki_name=cfg.wiki_name)
        return await exporter.export(export_target, destination)
    finally:
        await db.close()


async def run_capture_note(home: Path, note: str, *, event_type: str | None) -> RawSource | None:
    """Manually capture a research/decision dev event (no file changes)."""
    from datetime import UTC, datetime

    from wikiforge.activity.cost import CostTracker
    from wikiforge.ops.capture import capture_event

    if not (home / CONFIG_FILENAME).exists():
        return None
    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        try:
            llm = build_llm_provider(cfg, CostTracker(repo, cfg))
        except Exception:
            llm = None
        return await capture_event(
            repo, request=note, files=[], event_type=event_type, default_type="research",
            origin="manual", cfg=cfg, llm=llm, now=datetime.now(UTC),
        )
    finally:
        await db.close()


def _watermark_key(session_id: str, surface: str) -> str:
    """Namespace a capture watermark row by capturing surface.

    Stop, SubagentStop, and PreCompact all read the SAME transcript but consume
    COMPLEMENTARY turn sets (Stop/SubagentStop take edited turns, PreCompact
    takes file-less turns). A bare ``session_id`` key means whichever surface
    fires last silently overwrites the mark the others rely on, hiding each
    surface's own unconsumed turns from itself — see Finding 1 of the
    whole-branch review. Namespacing by surface is safe precisely because the
    turn sets are disjoint: a surface can only ever advance past turns it
    itself is responsible for, so per-surface marks cannot cause double-capture
    of the same turn by the same surface.
    """
    return f"{session_id}:{surface}"


async def run_capture_hook(home: Path, hook_stdin: str) -> RawSource | None:
    """Auto-capture a dev event from a Claude Code Stop-hook payload (best-effort)."""
    from datetime import UTC, datetime

    from wikiforge.activity.cost import CostTracker
    from wikiforge.ops.capture import (
        capture_event,
        default_git_runner,
        git_context,
        parse_hook_stdin,
    )
    from wikiforge.ops.recall import parse_hook_session_id
    from wikiforge.ops.transcript import last_entry_uuid, read_transcript, turns_since

    if not (home / CONFIG_FILENAME).exists():
        return None
    cfg = load_config(home)
    if not cfg.capture.auto:
        return None
    transcript_path = parse_hook_stdin(hook_stdin)
    if transcript_path is None:
        return None
    session_id = parse_hook_session_id(hook_stdin)
    entries = read_transcript(Path(transcript_path))
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        last_uuid = None
        watermark_key = None
        if session_id is not None:
            watermark_key = _watermark_key(session_id, "stop")
            await repo.ensure_capture_watermark()
            last_uuid = await repo.get_watermark(watermark_key)
        turns = turns_since(entries, last_uuid)
        edited = [t for t in turns if t.files]
        if not edited:
            return None
        try:
            llm = build_llm_provider(cfg, CostTracker(repo, cfg))
        except Exception:
            llm = None
        git_meta = git_context(default_git_runner)
        source: RawSource | None = None
        for turn in edited:
            captured = await capture_event(
                repo, request=turn.request, files=turn.files, event_type=None,
                default_type="change", origin="hook", cfg=cfg, llm=llm, now=datetime.now(UTC),
                git_meta=git_meta,
            )
            if captured is not None:
                source = captured
        if watermark_key is not None and source is not None:
            mark = edited[-1].uuid or last_entry_uuid(entries)
            if mark is not None:
                await repo.set_watermark(
                    watermark_key, mark, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                )
        return source
    finally:
        await db.close()


async def run_capture_subagent(home: Path, hook_stdin: str) -> RawSource | None:
    """Capture a subagent's work from a SubagentStop payload (best-effort, zero LLM-free path).

    Subagents run with their own transcript, so the main session's Stop hook
    never sees their edits. Their own session id — namespaced with the
    ``:subagent`` surface suffix (see :func:`_watermark_key`) — keys the
    watermark, which is what keeps parent and child from capturing the same
    work twice. Every edited turn since the watermark is captured (mirrors
    ``run_capture_hook``'s loop), not just the last one, so a subagent that
    makes several distinct edits doesn't silently lose all but the final turn.
    """
    from datetime import UTC, datetime

    from wikiforge.activity.cost import CostTracker
    from wikiforge.ops.capture import (
        capture_event,
        default_git_runner,
        git_context,
        parse_hook_stdin,
    )
    from wikiforge.ops.recall import parse_hook_session_id
    from wikiforge.ops.transcript import last_entry_uuid, read_transcript, turns_since

    if not (home / CONFIG_FILENAME).exists():
        return None
    cfg = load_config(home)
    if not cfg.capture.auto or not cfg.capture.subagents:
        return None
    transcript_path = parse_hook_stdin(hook_stdin)
    if transcript_path is None:
        return None
    session_id = parse_hook_session_id(hook_stdin)
    parent_raw = None
    try:
        parsed = json.loads(hook_stdin)
        parent_raw = parsed.get("parent_session_id") if isinstance(parsed, dict) else None
    except (ValueError, TypeError):
        parent_raw = None
    parent = parent_raw if isinstance(parent_raw, str) and parent_raw else None
    entries = read_transcript(Path(transcript_path))
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        last_uuid = None
        watermark_key = None
        if session_id is not None:
            watermark_key = _watermark_key(session_id, "subagent")
            await repo.ensure_capture_watermark()
            last_uuid = await repo.get_watermark(watermark_key)
        turns = turns_since(entries, last_uuid)
        edited = [t for t in turns if t.files]
        if not edited:
            return None
        try:
            llm = build_llm_provider(cfg, CostTracker(repo, cfg))
        except Exception:
            llm = None
        git_meta = git_context(default_git_runner)
        source: RawSource | None = None
        for turn in edited:
            captured = await capture_event(
                repo, request=turn.request, files=turn.files, event_type=None,
                default_type="change", origin="subagent", cfg=cfg, llm=llm,
                now=datetime.now(UTC), git_meta=git_meta,
                extra_provenance={"parent_session_id": parent} if parent else None,
            )
            if captured is not None:
                source = captured
        if watermark_key is not None and source is not None:
            mark = edited[-1].uuid or last_entry_uuid(entries)
            if mark is not None:
                await repo.set_watermark(
                    watermark_key, mark, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                )
        return source
    finally:
        await db.close()


async def run_capture_precompact(home: Path, hook_stdin: str) -> RawSource | None:
    """Capture the decisions a compaction is about to discard (zero LLM).

    ``run_capture_hook`` only records turns that edited files, so every
    conversational turn — the design discussion, the investigation, the
    rejected alternative — is invisible to the wiki today. PreCompact fires
    while the pre-compaction transcript is still intact, which is the last
    moment those turns can be saved.

    Unlike ``run_capture_hook``/``run_capture_subagent`` (one dev event per
    edited turn), this collapses every file-less turn since the watermark into
    a SINGLE event — a compaction sweep is a batch of context, not a sequence
    of discrete changes. The watermark still only advances when that single
    ``capture_event`` call actually returned a source (mirrors the Task 5/6
    fix): advancing on ``session_id`` alone would let a persistence failure
    silently discard the swept turns forever, since the next sweep only looks
    at turns *since* the watermark. The mark itself is keyed with the
    ``:precompact`` surface suffix (see :func:`_watermark_key`) so this sweep
    can never advance past — and hide from Stop/SubagentStop — turns that carry
    file edits; PreCompact only ever consumes file-less turns, so it only ever
    marks up to the last file-less turn it actually consumed.
    """
    from datetime import UTC, datetime

    from wikiforge.activity.cost import CostTracker
    from wikiforge.ops.capture import (
        capture_event,
        default_git_runner,
        git_context,
        parse_hook_stdin,
    )
    from wikiforge.ops.recall import parse_hook_session_id
    from wikiforge.ops.transcript import last_entry_uuid, read_transcript, turns_since

    if not (home / CONFIG_FILENAME).exists():
        return None
    cfg = load_config(home)
    if not cfg.capture.auto or not cfg.capture.precompact:
        return None
    transcript_path = parse_hook_stdin(hook_stdin)
    if transcript_path is None:
        return None
    session_id = parse_hook_session_id(hook_stdin)
    entries = read_transcript(Path(transcript_path))
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        last_uuid = None
        watermark_key = None
        if session_id is not None:
            watermark_key = _watermark_key(session_id, "precompact")
            await repo.ensure_capture_watermark()
            last_uuid = await repo.get_watermark(watermark_key)
        fileless = [t for t in turns_since(entries, last_uuid) if not t.files]
        if not fileless:
            return None
        blocks: list[str] = []
        for turn in fileless:
            blocks.append(f"### {turn.request}")
            if turn.assistant_text:
                blocks.append(turn.assistant_text)
        payload = "\n\n".join(blocks)[: cfg.capture.precompact_max_chars]
        try:
            llm = build_llm_provider(cfg, CostTracker(repo, cfg))
        except Exception:
            llm = None
        git_meta = git_context(default_git_runner)
        source = await capture_event(
            repo, request=payload, files=[], event_type=None,
            default_type="research", origin="precompact", cfg=cfg, llm=llm,
            now=datetime.now(UTC), git_meta=git_meta,
            extra_provenance={"turns": str(len(fileless))},
        )
        if watermark_key is not None and source is not None:
            mark = fileless[-1].uuid or last_entry_uuid(entries)
            if mark is not None:
                await repo.set_watermark(
                    watermark_key, mark, datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
                )
        return source
    finally:
        await db.close()


async def run_recall_hook(home: Path, hook_stdin: str) -> str:
    """Return sealed wiki excerpts for a UserPromptSubmit payload; "" on any skip.

    Fast path: bail out before touching the embedding stack when the wiki DB
    is absent or holds no chunks, so non-wiki projects pay ~0 ms per prompt.
    """
    from wikiforge.federation.fanout import active_peers
    from wikiforge.ops.recall import (
        classify_route,
        parse_hook_session_id,
        parse_prompt_hook_stdin,
        recall_excerpts,
        route_hint_line,
        should_recall,
    )
    from wikiforge.search.retriever import HybridRetriever
    from wikiforge.storage.db import DB_FILENAME

    if not (home / CONFIG_FILENAME).exists():
        return ""
    cfg = load_config(home)
    if not cfg.recall.enabled:
        return ""
    prompt = parse_prompt_hook_stdin(hook_stdin)
    if prompt is None or not should_recall(prompt):
        return ""
    hint = ""
    if cfg.recall.routing_hint:
        label = classify_route(prompt)
        if label is not None:
            hint = route_hint_line(label)
    excerpts = ""
    if (home / DB_FILENAME).exists():
        db = await Database.open(home, dim=effective_embedding_dim(cfg))
        try:
            repo = Repository(db)
            if await repo.has_chunks():
                embedder = build_embedding_provider(cfg, repo)
                await ensure_embedding_compat(repo, embedder)
                retriever = HybridRetriever(repo, embedder, cfg)
                excerpts = await recall_excerpts(
                    repo,
                    retriever,
                    embedder,
                    cfg,
                    prompt,
                    peers=active_peers(cfg),
                    dim=effective_embedding_dim(cfg),
                    session_id=parse_hook_session_id(hook_stdin),
                )
        finally:
            await db.close()
    if excerpts and hint:
        return f"{excerpts}\n\n{hint}"
    return excerpts or hint


async def run_why(
    home: Path, path: str, *, limit: int = 5
) -> tuple[list[Sourced[RawSource]], bool]:
    """Decision history for ``path``, newest first, scoped to the current repo.

    Returns ``(events, fell_back)``. A relative path is anchored to the
    enclosing git worktree so a wiki shared by several projects cannot answer
    with another project's decisions; ``fell_back`` is True when that repo had
    no history and the ``/``-anchored suffix match answered instead, which the
    caller must label rather than pass off as local history. An absolute path
    is looked up as given — the PreToolUse guardrail always supplies one.

    Never constructs an embedding or LLM provider — the lookup is pure SQL over
    the ``dev_event_files`` index (ensured + backfilled on first use). A home
    with no config or no database returns ``([], False)``.

    Federated (cycle 4): the local read runs first, with ``read_only=False`` so
    this wiki's own index is still ensured/backfilled exactly as before. Every
    active peer (``[federation] enabled`` plus the machine-global registry) is
    then read with ``read_only=True`` — a peer is never written to — and merged
    in, newest-first by :func:`~wikiforge.ops.why.event_ts`, with the combined
    list capped to ``limit`` (each wiki may itself return up to ``limit``).
    ``fell_back`` still describes only the local lookup; a peer's contribution
    is signalled per-event via ``Sourced.origin``, not by this flag.
    """
    from wikiforge.federation.fanout import Sourced, active_peers, fan_out
    from wikiforge.ops.why import event_ts
    from wikiforge.storage.db import DB_FILENAME

    if not (home / CONFIG_FILENAME).exists() or not (home / DB_FILENAME).exists():
        return [], False
    cfg = load_config(home)
    root = repo_root()
    dim = effective_embedding_dim(cfg)

    async def read(repo: Repository, *, read_only: bool) -> list[RawSource]:
        if path.startswith("/"):
            return await events_for_absolute(repo, path, limit=limit, read_only=read_only)
        found = await events_for_paths(repo, [path], root=root, limit=limit, read_only=read_only)
        return found.events

    db = await Database.open(home, dim=dim)
    try:
        local_repo = Repository(db)
        fell_back = False
        if path.startswith("/"):
            local_events = await events_for_absolute(local_repo, path, limit=limit, read_only=False)
        else:
            found = await events_for_paths(
                local_repo, [path], root=root, limit=limit, read_only=False
            )
            local_events = found.events
            fell_back = found.fell_back
        merged = [Sourced(origin="", item=e) for e in local_events]
        merged.extend(
            await fan_out(
                active_peers(cfg),
                lambda repo: read(repo, read_only=True),
                local=None,
                dim=dim,
                timeout_ms=cfg.federation.peer_timeout_ms,
            )
        )
    finally:
        await db.close()
    merged.sort(key=lambda s: event_ts(s.item), reverse=True)
    return merged[:limit], fell_back


async def run_why_hook(home: Path, hook_stdin: str) -> str:
    """Return a sealed decision-history warning for a PreToolUse payload; "" on any skip.

    Zero LLM, zero embeddings, allow-only (the guardrail informs, never gates).
    Skips silently when: no config, guardrail disabled, no DB, unparseable
    payload, no decision-carrying events for the file — locally OR on any peer,
    see below — or this session was already warned about this file.

    Federated (cycle 4): local events are fetched and type-filtered exactly as
    before, then every active peer is read (``read_only=True`` — a peer is
    never written to) and merged in, newest-first, before the "nothing to warn
    about" check. That check deliberately runs on the merged list rather than
    on local results alone: a file with no local history but real history on a
    peer must still warn.
    """
    from datetime import UTC, datetime, timedelta

    from wikiforge.federation.fanout import Sourced, active_peers, fan_out
    from wikiforge.ops.why import event_ts, parse_pretool_stdin, render_warning
    from wikiforge.storage.db import DB_FILENAME

    if not (home / CONFIG_FILENAME).exists():
        return ""
    cfg = load_config(home)
    if not cfg.why.guardrail:
        return ""
    path, session_id = parse_pretool_stdin(hook_stdin)
    if path is None:
        return ""
    if not (home / DB_FILENAME).exists():
        return ""
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        await repo.ensure_dev_event_files()
        events = await repo.dev_events_for_path(path, limit=25)
        events = [
            e for e in events
            if cfg.why.warns_for(e.provenance.get("type") or "change")
        ]

        async def peer_read(peer_repo: Repository) -> list[RawSource]:
            found = await events_for_absolute(peer_repo, path, limit=25, read_only=True)
            return [e for e in found if cfg.why.warns_for(e.provenance.get("type") or "change")]

        merged = [Sourced(origin="", item=e) for e in events]
        merged.extend(
            await fan_out(
                active_peers(cfg),
                peer_read,
                local=None,
                dim=effective_embedding_dim(cfg),
                timeout_ms=cfg.federation.peer_timeout_ms,
            )
        )
        merged.sort(key=lambda s: event_ts(s.item), reverse=True)
        if not merged:
            return ""
        now = datetime.now(UTC)
        if session_id is not None:
            await repo.ensure_why_log()
            await repo.purge_why_log(
                (now - timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
            )
            try:
                await repo.ensure_capture_watermark()
                await repo.purge_watermarks(
                    (now - timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%SZ")
                )
            except Exception:
                pass  # opportunistic hygiene only — must never break the guardrail
            if await repo.why_warned(session_id, path):
                return ""
        warning = render_warning(merged, max_events=cfg.why.guardrail_max_events)
        if not warning:
            return ""
        if session_id is not None:
            await repo.log_why_warning(
                session_id, path, now.strftime("%Y-%m-%dT%H:%M:%SZ")
            )
        return warning
    finally:
        await db.close()


async def run_peers_add(home: Path, target: str, *, alias: str | None) -> PeerRef:
    """Register ``target`` as a peer of the machine-global registry.

    Validates before writing so the registry never holds an entry that cannot
    be opened: the path must be a wiki, must not be this wiki, and must not
    already be registered under any alias. Both paths are resolved before
    comparison so a trailing slash or ``..`` segment cannot disguise the local
    wiki as a distinct peer (spec §4.3 forbids self-federation, which would
    double every fan-out result).
    """
    from wikiforge.federation.registry import load_registry, save_registry, slugify_alias
    from wikiforge.storage.db import DB_FILENAME

    peer_home = Path(target).expanduser().resolve()
    if not (peer_home / CONFIG_FILENAME).exists() or not (peer_home / DB_FILENAME).exists():
        raise ValueError(f"{peer_home} is not a wiki (needs config.toml and wiki.db)")
    if peer_home == home.expanduser().resolve():
        raise ValueError("a wiki cannot be a peer of itself")

    peers = load_registry()
    if any(p.home.expanduser().resolve() == peer_home for p in peers):
        raise ValueError(f"{peer_home} is already registered")

    chosen = alias or slugify_alias(load_config(peer_home).wiki_name)
    taken = {p.alias for p in peers}
    if chosen in taken:
        if alias is not None:
            raise ValueError(f"alias {chosen!r} is already registered")
        # Only an auto-derived alias may collide silently (two wikis happen to
        # share a wiki_name) — an explicit --alias collision is the user's
        # mistake and must be rejected above, not renamed out from under them.
        suffix = 2
        while f"{chosen}-{suffix}" in taken:
            suffix += 1
        chosen = f"{chosen}-{suffix}"

    ref = PeerRef(alias=chosen, home=peer_home)
    save_registry([*peers, ref])
    return ref


async def run_peers_rm(alias: str) -> bool:
    """Remove one peer from the registry by alias.

    Takes no ``home``: the registry is machine-global rather than per-project,
    so removing a peer never depends on which wiki the caller is standing in.
    Returns False instead of raising when the alias isn't registered, so the
    CLI can report a plain "no such peer" error rather than an exception.
    """
    from wikiforge.federation.registry import load_registry, save_registry

    peers = load_registry()
    kept = [p for p in peers if p.alias != alias]
    if len(kept) == len(peers):
        return False
    save_registry(kept)
    return True


async def run_peers_list(home: Path) -> tuple[list[PeerStatus], str | None]:
    """Probe every registered peer's reachability and embedding compatibility.

    Opens the *local* wiki only to resolve which embedding model this process
    would currently use — read from live config, not stamped meta, since the
    question is "would a peer fuse cleanly right now", not history — then
    probes each peer against it via :func:`~wikiforge.federation.peers.peer_status`,
    which never raises. A malformed ``peers.toml`` is returned as an error
    string rather than raised, so one bad line degrades `wiki peers list` to a
    warning instead of taking the whole command down.
    """
    from wikiforge.federation.peers import peer_status
    from wikiforge.federation.registry import load_registry_report

    cfg = load_config(home)
    dim = effective_embedding_dim(cfg)
    db = await Database.open(home, dim=dim)
    try:
        embedder = build_embedding_provider(cfg, Repository(db))
        local_model = embedder.model
    finally:
        await db.close()
    peers, error = load_registry_report()
    return [await peer_status(p, local_model=local_model, dim=dim) for p in peers], error


async def run_capture_flush(home: Path, *, digests: bool) -> FlushStats:
    """Backfill dev-log vectors; with ``digests`` also batch-summarize pending events."""
    from wikiforge.activity.cost import CostTracker
    from wikiforge.ops.flush import flush_dev_events

    if not (home / CONFIG_FILENAME).exists():
        return FlushStats(embedded_chunks=0, digested_events=0, pending_left=0)
    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        tracker = CostTracker(repo, cfg)
        embedder = build_embedding_provider(cfg, repo, cost_tracker=tracker)
        await ensure_embedding_compat(repo, embedder)
        auto_batches = cfg.capture.auto_digest_batches
        want_digests = digests or auto_batches > 0
        llm = None
        if want_digests:
            try:
                llm = build_llm_provider(cfg, tracker)
            except Exception:
                llm = None
        return await flush_dev_events(
            repo, embedder, llm, cfg,
            digests=want_digests,
            max_batches=None if digests else auto_batches,
        )
    finally:
        await db.close()


async def run_maintain(home: Path, *, dry_run: bool = False, force: bool = False) -> MaintainReport:
    """Run automatic maintenance for one wiki within its window budget.

    ``force`` lifts the ceilings for this run only — an explicit human
    override; the spend is still recorded and still counts against later runs.
    Returns an empty report when the wiki is missing or maintenance is off, so
    the hook path has nothing to catch.
    """
    from wikiforge.activity.cost import CostTracker
    from wikiforge.llm.governed import Budget
    from wikiforge.ops.maintain import JobContext, run_jobs
    from wikiforge.storage.db import DB_FILENAME

    if not (home / CONFIG_FILENAME).exists() or not (home / DB_FILENAME).exists():
        return MaintainReport(outcomes=[], calls_used=0, usd_used=0.0, calls_left=0)
    cfg = load_config(home)
    if not cfg.maintain.enabled:
        return MaintainReport(outcomes=[], calls_used=0, usd_used=0.0, calls_left=0)

    budget = Budget(
        max_calls=10**9 if force else cfg.maintain.max_calls_24h,
        max_usd=float("inf") if force else cfg.maintain.max_usd_24h,
        window_hours=cfg.maintain.window_hours,
    )
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        tracker = CostTracker(repo, cfg)
        try:
            llm = build_llm_provider(cfg, tracker)
        except Exception:
            llm = None
        ctx = JobContext(home=home, cfg=cfg, repo=repo, tracker=tracker, llm=llm)
        report = await run_jobs(ctx, names=list(cfg.maintain.jobs), budget=budget, dry_run=dry_run)
        if not dry_run:
            done = sum(1 for o in report.outcomes if o.status == "done")
            await ActivityRecorder(repo).record(
                "maintain",
                {"jobs": ",".join(o.name for o in report.outcomes if o.status == "done")},
                summary=f"{done} job(s) done, {report.calls_used} call(s) used in window",
            )
        return report
    finally:
        await db.close()


async def run_consolidate(home: Path, *, only_if_auto: bool = False) -> ConsolidateStats:
    """Roll old dev events into the development-log article (one cheap call per period).

    ``only_if_auto`` is the SessionStart entry: a no-op unless ``[consolidate]
    auto = true``. Returns zero stats when no LLM backend can be built.
    """
    from datetime import UTC, datetime

    from wikiforge.activity.cost import CostTracker
    from wikiforge.ops.consolidate import ConsolidateStats, consolidate_dev_log

    if not (home / CONFIG_FILENAME).exists():
        return ConsolidateStats(periods=0, events=0)
    cfg = load_config(home)
    if only_if_auto and not cfg.consolidate.auto:
        return ConsolidateStats(periods=0, events=0)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        tracker = CostTracker(repo, cfg)
        embedder = build_embedding_provider(cfg, repo, cost_tracker=tracker)
        await ensure_embedding_compat(repo, embedder)
        try:
            llm = build_llm_provider(cfg, tracker)
        except Exception:
            return ConsolidateStats(periods=0, events=0)
        return await consolidate_dev_log(
            repo, embedder, llm, cfg, home, now=datetime.now(UTC)
        )
    finally:
        await db.close()


async def run_changelog(
    home: Path,
    spec: str | None,
    *,
    limit: int = 50,
    exclude_types: frozenset[str] = frozenset(),
    prose: bool = False,
) -> str:
    """Render a why-annotated changelog for a git range.

    Zero LLM unless ``prose`` is set, in which case one cheap call rewrites the
    structured render. A prose failure degrades to the structured output rather
    than losing it.

    Federated (cycle 4): after the local two-arm selection, every active peer
    (``[federation] enabled`` plus the machine-global registry) runs the same
    selection read-only via
    :func:`~wikiforge.ops.changelog.select_peer_events` and contributes its
    events, labelled with the peer's alias and re-sorted newest-first into the
    merged list. A peer never touches ``files_with_history`` or ``excluded``:
    those describe how much of *this wiki's* own range this wiki explains, and
    a peer answering part of it does not change that denominator.
    """
    from wikiforge.activity.cost import CostTracker
    from wikiforge.ops import changelog as changelog_ops

    root = repo_root()
    if not root:
        raise ValueError("changelog needs a git repository")
    rng = changelog_ops.resolve_range(spec)

    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        log = await changelog_ops.build_changelog(
            repo, rng, root=root, limit=limit, exclude_types=exclude_types
        )

        from collections import Counter
        from dataclasses import replace

        from wikiforge.federation.fanout import active_peers, fan_out

        peer_sourced = await fan_out(
            active_peers(cfg),
            lambda peer_repo: changelog_ops.select_peer_events(
                peer_repo, rng, root=root, limit=limit, exclude_types=exclude_types
            ),
            local=None,
            dim=effective_embedding_dim(cfg),
            timeout_ms=cfg.federation.peer_timeout_ms,
        )
        if peer_sourced:
            merged = list(log.entries) + [
                changelog_ops.ChangelogEntry(
                    event=s.item.event, matched_by=s.item.matched_by, origin=s.origin
                )
                for s in peer_sourced
            ]
            merged.sort(key=lambda entry: entry.event.fetched_at, reverse=True)
            log = replace(log, entries=merged, by_origin=dict(Counter(e.origin for e in merged)))

        rendered = changelog_ops.format_changelog(log)
        if not prose:
            return rendered
        try:
            llm = build_llm_provider(cfg, CostTracker(repo, cfg))
            return await changelog_ops.compose_prose(llm, cfg, rendered)
        except Exception as exc:  # noqa: BLE001 - a failed nicety must not lose data
            import sys

            print(f"note: prose generation failed ({exc}); showing the structured changelog",
                  file=sys.stderr)
            return rendered
    finally:
        await db.close()


async def run_impact(
    home: Path, target: str, *, limit: int = 20, as_kind: str | None = None
) -> str:
    """Render the blast radius of a source, a file, or a topic.

    Read-only and zero-LLM. ``as_kind`` forces the interpretation when the
    automatic classification would guess wrong (a topic slug that looks like a
    filename, say). Raises ``ValueError`` for an ``as_kind`` other than
    "source", "file", or "topic" — checked here, at the shared service layer,
    so every caller (CLI and MCP alike) is protected even if a presentation
    layer forgets its own check.

    Federated (cycle 4), file target only: every active peer contributes its
    own decision history for the same path, read-only, merged in newest-first
    and labelled with the peer's alias. Source and topic targets stay local —
    merging citation or topic-graph data across wikis needs cross-wiki topic
    identity, an explicit non-goal (spec §3).
    """
    from wikiforge.ops import impact as impact_ops

    if as_kind is not None and as_kind not in ("source", "file", "topic"):
        raise ValueError(f"--as must be one of: source, file, topic (got {as_kind!r})")
    kind = impact_ops.classify_target(target, forced=as_kind)  # type: ignore[arg-type]
    cfg = load_config(home)
    db = await Database.open(home, dim=effective_embedding_dim(cfg))
    try:
        repo = Repository(db)
        if kind == "source":
            source = await _resolve_source(repo, target)
            if source is None:
                raise ValueError(
                    f"no source matches {target!r} (tried url/hash/id) — "
                    "use --as file or --as topic to force another reading"
                )
            return impact_ops.format_impact(
                await impact_ops.build_source_impact(repo, source, limit=limit)
            )
        if kind == "file":
            from dataclasses import replace

            from wikiforge.federation.fanout import active_peers, fan_out

            report = await impact_ops.build_file_impact(repo, target, root=repo_root(), limit=limit)

            async def _peer_file_events(peer_repo: Repository) -> list[RawSource]:
                found = await events_for_paths(
                    peer_repo, [target], root=repo_root(), limit=limit, read_only=True
                )
                return found.events

            peer_sourced = await fan_out(
                active_peers(cfg),
                _peer_file_events,
                local=None,
                dim=effective_embedding_dim(cfg),
                timeout_ms=cfg.federation.peer_timeout_ms,
            )
            if peer_sourced:
                merged = list(report.events) + list(peer_sourced)
                merged.sort(key=lambda s: s.item.fetched_at, reverse=True)
                report = replace(report, events=merged)
            return impact_ops.format_impact(report)
        topic = await repo.get_topic(target)
        if topic is None:
            raise ValueError(
                f"no topic matches {target!r} — "
                "use --as file or --as source to force another reading"
            )
        return impact_ops.format_impact(
            await impact_ops.build_topic_impact(repo, topic, limit=limit)
        )
    finally:
        await db.close()


async def _resolve_source(repo: Repository, target: str) -> RawSource | None:
    """Resolve a source target by URL, content hash, or numeric id."""
    if target.startswith(("http://", "https://")):
        return await repo.get_raw_source_by_url(target)
    digits = target.removeprefix("#")
    if digits.isdigit():
        return await repo.get_raw_source_by_id(int(digits))
    return await repo.get_raw_source_by_hash(target)

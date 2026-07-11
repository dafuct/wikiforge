"""The shared service layer. Both the CLI and the MCP server call these functions.

Milestone 1 provides ``init_wiki``; Milestone 2 adds ``ingest_source`` and
``detect_target_kind``. Later milestones extend this module further.
"""

from __future__ import annotations

from pathlib import Path

import httpx

from wikiforge.activity.recorder import ActivityRecorder
from wikiforge.config.settings import (
    CONFIG_FILENAME,
    load_config,
    write_default_config,
)
from wikiforge.embed.provider import EmbeddingProvider
from wikiforge.ingest import sources as ingest_sources
from wikiforge.models.domain import RawSource
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

    db = await Database.open(home, dim=cfg.embedding.dim)
    try:
        await db.init_schema()
        recorder = ActivityRecorder(Repository(db))
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

    ``_db`` is a test-only seam: production callers always open their own
    ``Database`` from ``home`` (and this function closes it before returning).
    Tests pass an already-open database so they can assert on it afterward; in
    that case this function neither opens nor closes it.
    """
    kind = detect_target_kind(target)
    if kind == "url":
        source = await ingest_sources.ingest_url(target, client=http_client)
    elif kind == "pdf":
        source = ingest_sources.ingest_pdf(Path(target))
    else:
        source = ingest_sources.ingest_file(Path(target))

    db = _db or await Database.open(home, dim=embedder.dim)
    try:
        repo = Repository(db)
        source_id, created = await repo.ingest_raw_source(source)
        stored = await repo.get_raw_source_by_hash(source.content_hash)
        assert stored is not None
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

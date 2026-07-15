"""Flush: dev-log vector backfill (always) + batch digests (opt-in), per-item salvage."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import ParsedResult
from wikiforge.ops.capture import capture_event
from wikiforge.ops.flush import BatchDigestItem, BatchDigestOut, FlushStats, flush_dev_events
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_NOW = datetime(2026, 7, 15, 9, 0, 0, tzinfo=UTC)
_LONG = "please investigate and rework the retriever " + "x" * 300


class DimEmbedder:
    """Deterministic 4-dim embedder for tests."""

    dim = 4
    model = "fake"
    provider_name = "fake"

    async def embed(self, texts):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


class _BatchLLM:
    def __init__(self, out: BatchDigestOut):
        self._out = out
        self.calls = 0

    async def parse(self, purpose, system, user, *, tier=None, schema, topic_id=None,
                    session_id=None):
        self.calls += 1
        assert tier == "cheap"
        assert "<source_data" in user
        return ParsedResult(parsed=self._out, input_tokens=1, output_tokens=1, model="fake")

    async def complete(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


async def _wiki(tmp_path: Path):
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="Test")
    cfg = load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    return db, Repository(db), cfg


async def _pending_event(repo, cfg) -> int:
    src = await capture_event(
        repo, request=_LONG, files=["a.py"], event_type=None, default_type="change",
        origin="hook", cfg=cfg, llm=None, now=_NOW, git_runner=lambda argv: "",
    )
    assert src is not None and src.provenance["digest"] == "pending"
    assert src.id is not None
    return src.id


async def test_flush_backfills_vectors_without_digests(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    try:
        await _pending_event(repo, cfg)
        assert await repo.chunks_missing_vectors(owner_type="raw_source", limit=10)
        stats = await flush_dev_events(repo, DimEmbedder(), None, cfg, digests=False)
        assert stats.embedded_chunks > 0
        assert stats.digested_events == 0
        assert stats.pending_left == 1  # digest still pending — no LLM was allowed
        assert await repo.chunks_missing_vectors(owner_type="raw_source", limit=10) == []
    finally:
        await db.close()


async def test_flush_digests_applies_summary_to_provenance_and_index(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    try:
        sid = await _pending_event(repo, cfg)
        llm = _BatchLLM(BatchDigestOut(items=[
            BatchDigestItem(id=sid, summary="Reworked the retriever.", type="refactor"),
        ]))
        stats = await flush_dev_events(repo, DimEmbedder(), llm, cfg, digests=True)
        assert stats == FlushStats(embedded_chunks=stats.embedded_chunks, digested_events=1,
                                   pending_left=0)
        events = await repo.dev_events_pending_digest(limit=10)
        assert events == []
        rows = await db.fetchall(
            "SELECT text FROM chunks WHERE owner_type='raw_source' AND owner_id=?", (sid,)
        )
        assert any("Reworked the retriever." in r["text"] for r in rows)  # summary searchable
    finally:
        await db.close()


async def test_flush_salvages_partial_batch(tmp_path: Path) -> None:
    db, repo, cfg = await _wiki(tmp_path)
    try:
        sid = await _pending_event(repo, cfg)
        llm = _BatchLLM(BatchDigestOut(items=[
            BatchDigestItem(id=sid, summary="Good.", type="refactor"),
            BatchDigestItem(id=999999, summary="Ghost.", type="feature"),   # unknown id ignored
            BatchDigestItem(id=sid, summary="Bad type.", type="nonsense"),  # invalid type ignored
        ]))
        stats = await flush_dev_events(repo, DimEmbedder(), llm, cfg, digests=True)
        assert stats.digested_events == 1
        assert stats.pending_left == 0
    finally:
        await db.close()

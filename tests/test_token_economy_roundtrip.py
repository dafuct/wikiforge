"""End-to-end: a captured dev event is flushed (vectors+digest) and recalled by meaning."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import ParsedResult
from wikiforge.ops.capture import capture_event
from wikiforge.ops.flush import BatchDigestItem, BatchDigestOut, flush_dev_events
from wikiforge.ops.recall import recall_excerpts
from wikiforge.query.service import RECALL_HEADER
from wikiforge.search.retriever import HybridRetriever
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_NOW = datetime(2026, 7, 15, 9, 0, 0, tzinfo=UTC)
_REQUEST = (
    "we hit a deadlock with async callbacks in the UniFFI bridge, so rework it "
    "to use a synchronous queue instead " + "x" * 200
)


class ConcurrencyEmbedder:
    """dim-4: axis 0 fires on concurrency words — so 'паралельність' ≈ 'deadlock'."""

    dim = 4
    model = "fake"
    provider_name = "fake"

    async def embed(self, texts):
        words = ("deadlock", "concurrency", "паралельн", "async")
        return [
            [1.0 if any(w in t.lower() for w in words) else 0.0, 0.0, 0.0, 0.1]
            for t in texts
        ]


class _OneShotBatchLLM:
    def __init__(self, sid: int):
        self._sid = sid

    async def parse(self, purpose, system, user, *, tier=None, schema, topic_id=None,
                    session_id=None):
        out = BatchDigestOut(items=[BatchDigestItem(
            id=self._sid, summary="Adopted a blocking dispatch model to remove the "
            "race condition.", type="refactor")])
        return ParsedResult(parsed=out, input_tokens=1, output_tokens=1, model="fake")

    async def complete(self, *a, **k):  # pragma: no cover
        raise NotImplementedError


async def test_saved_then_found(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="Test")
    cfg = load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    try:
        repo = Repository(db)
        embedder = ConcurrencyEmbedder()

        # 1. Capture (deferred default): zero LLM, digest pending.
        src = await capture_event(
            repo, request=_REQUEST, files=["bridge.rs"], event_type=None,
            default_type="change", origin="hook", cfg=cfg, llm=None, now=_NOW,
            git_runner=lambda argv: "",
        )
        assert src is not None
        assert src.provenance["digest"] == "pending"
        assert src.id is not None

        # 2. Flush with digests: vectors backfilled, summary applied.
        stats = await flush_dev_events(
            repo, embedder, _OneShotBatchLLM(src.id), cfg, digests=True
        )
        assert stats.embedded_chunks > 0
        assert stats.digested_events == 1

        # 3. Recall with DIFFERENT words ("паралельність", not "deadlock").
        # Retrieval fires on event.text's own concurrency words ("deadlock"/"async"),
        # not on the digest summary — so this proves semantic recall works regardless
        # of digest content.
        retriever = HybridRetriever(repo, embedder, cfg)
        out = await recall_excerpts(
            retriever, embedder, cfg, "у нас проблема з паралельністю в мості, що робити?"
        )
        assert out.startswith(RECALL_HEADER)
        assert "synchronous queue" in out          # raw request text came back semantically
        # This phrase exists ONLY in the digest summary (never in _REQUEST or other
        # rendered note sections), so its presence proves the digest content itself —
        # not just the raw request text — survived flush's re-index into recall.
        assert "blocking dispatch" in out
    finally:
        await db.close()

"""Federated recall: peer excerpts are scored in their own wiki and capped after merge."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.config.settings import load_config
from wikiforge.federation.fanout import Sourced, active_peers
from wikiforge.federation.registry import PeerRef, save_registry
from wikiforge.ops.recall import recall_excerpts
from wikiforge.query.service import render_excerpts
from wikiforge.search.retriever import HybridRetriever
from wikiforge.search.rrf import ChunkTarget
from wikiforge.services import init_wiki
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


def _target(rowid: int, *, text: str, owner_id: int = 7) -> ChunkTarget:
    return ChunkTarget(
        rowid=rowid,
        owner_type="article",
        owner_id=owner_id,
        seq=2,
        text=text,
        topic_id=None,
        topic_status=None,
        article_confidence=0.8,
    )


def test_local_render_is_unchanged() -> None:
    """No peers means byte-identical output to the pre-cycle-4 renderer."""
    out = render_excerpts([Sourced("", _target(1, text="hello"))])
    assert "<source_data id='article:7#2'>hello</source_data>" in out
    assert "/" not in out.split("id='")[1].split("'")[0]


def test_peer_block_id_carries_the_alias() -> None:
    """A peer excerpt is identifiable in the model's context."""
    out = render_excerpts([Sourced("global", _target(1, text="hello"))])
    assert "<source_data id='global/article:7#2'>" in out


def test_peer_annotation_names_the_origin() -> None:
    """The epistemic line already exists; origin joins it as trusted metadata."""
    out = render_excerpts(
        [Sourced("global", _target(1, text="hello"))],
        annotate=True,
        now=datetime.now(UTC),
    )
    assert "from global" in out.split("<source_data")[0]


def test_cap_is_applied_after_the_merge() -> None:
    """Federation changes which excerpts arrive, never how many (spec §7.1)."""
    from wikiforge.ops.recall import cap_and_dedup

    scored = [
        (0.95, Sourced("global", _target(1, text="p1"))),
        (0.94, Sourced("", _target(2, text="l1", owner_id=1))),
        (0.93, Sourced("global", _target(3, text="p2", owner_id=2))),
    ]
    kept = cap_and_dedup(scored, seen=set(), max_excerpts=2)
    assert [s.item.text for s in kept] == ["p1", "l1"]


def test_zero_max_excerpts_admits_nothing() -> None:
    """A user can legally set [recall] max_excerpts = 0 to disable injection
    while keeping other recall behavior (e.g. routing_hint) active — the cap
    must be checked before admitting a candidate, not after."""
    from wikiforge.ops.recall import cap_and_dedup

    scored = [(0.9, Sourced("", _target(1, text="a")))]
    assert cap_and_dedup(scored, seen=set(), max_excerpts=0) == []


def test_dedup_is_origin_aware() -> None:
    """A peer chunk whose ids collide with an already-seen local one survives."""
    from wikiforge.ops.recall import cap_and_dedup

    scored = [(0.9, Sourced("global", _target(1, text="peer")))]
    kept = cap_and_dedup(scored, seen={("", "article", 7, 2)}, max_excerpts=3)
    assert [s.item.text for s in kept] == ["peer"]
    kept2 = cap_and_dedup(scored, seen={("global", "article", 7, 2)}, max_excerpts=3)
    assert kept2 == []


# --- End-to-end: a peer chunk is scored inside its own repository -----------

# 384 = the default local embedding dim (settings.py EmbeddingConfig.local_dim),
# which is what `init_wiki` sizes a fresh wiki's chunks_vec table to. Using
# anything else would need a config override just to avoid a vec0 dimension
# mismatch, so the fixed vectors below just match the real default.
_QUERY_VEC = [1.0] + [0.0] * 383


class _FixedEmbedder:
    """Always embeds to the same 384-dim vector — dimension matches the real
    default schema (see ``_QUERY_VEC``) so both wikis' genuine vec0 tables
    (built via ``init_wiki``) accept it without a reindex."""

    dim = 384
    model = "fake"
    provider_name = "fake"

    async def embed(self, texts, *, kind="passage"):
        return [list(_QUERY_VEC) for _ in texts]


async def _build_wiki(home: Path, *, text: str, vector: list[float], model: str = "fake") -> None:
    """Create a real wiki with one indexed chunk (FTS row + stored vector),
    stamped with an embedding model so a peer read can pass the compat gate.

    Same shape as Task 1's ``_build_wiki`` (``tests/test_federation_probe.py``,
    column names verified there against the real schema), plus the
    ``embedding_model`` meta stamp ``compat_verdict`` needs. Every wiki built
    by this helper reuses ``rowid=1`` for its one chunk on purpose: if scoring
    ever read one wiki's rowid against a DIFFERENT wiki's ``chunk_vectors``,
    rowid 1 would still resolve (it exists in both databases) but to the WRONG
    vector/text — so a rowid-crossing bug fails these assertions instead of
    passing by accident.
    """
    await init_wiki("w", home)
    db = await Database.open(home, dim=len(vector))
    try:
        conn = db.conn
        repo = Repository(db)
        await conn.execute(
            "INSERT INTO raw_sources"
            " (id, content_hash, source_type, title, text, fetched_at, provenance)"
            " VALUES (1, 'probe-hash', 'dev_event', 'probe', :text,"
            " '2026-07-21T00:00:00+00:00', '{}')",
            {"text": text},
        )
        await conn.execute(
            "INSERT INTO chunks (rowid, owner_type, owner_id, seq, text, content_hash)"
            " VALUES (1, 'raw_source', 1, 0, :text, 'chunk-hash')",
            {"text": text},
        )
        await conn.execute("INSERT INTO chunks_fts (rowid, text) VALUES (1, :text)", {"text": text})
        await conn.execute(
            "INSERT INTO chunks_vec (rowid, embedding) VALUES (1, :vec)",
            {"vec": json.dumps(vector)},
        )
        await repo.set_meta("embedding_model", model)
        await conn.commit()
    finally:
        await db.close()


async def test_recall_excerpts_admits_a_peer_chunk_scored_inside_its_own_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A peer's chunk reaches the output; only its (score, Sourced) pair crossed fan_out.

    The local wiki's one chunk is orthogonal to the query vector (similarity
    0.0, gated out by ``min_similarity``); the peer's is identical to it
    (similarity 1.0, the best possible match) — so the excerpt in the output
    can only have come from scoring that ran inside the PEER's own repository.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    local_home = tmp_path / "local"
    peer_home = tmp_path / "peer"
    await _build_wiki(local_home, text="unrelated grocery note", vector=[0.0, 1.0] + [0.0] * 382)
    await _build_wiki(peer_home, text="deadlock retry strategy chosen", vector=list(_QUERY_VEC))
    save_registry([PeerRef("global", peer_home)])

    embedder = _FixedEmbedder()
    cfg = load_config(local_home)
    db = await Database.open(local_home, dim=384)
    try:
        repo = Repository(db)
        retriever = HybridRetriever(repo, embedder, cfg)
        out = await recall_excerpts(
            repo,
            retriever,
            embedder,
            cfg,
            "why did we hit a deadlock in the bridge?",
            peers=active_peers(cfg),
            dim=384,
            now=datetime(2026, 7, 21, tzinfo=UTC),
        )
    finally:
        await db.close()

    assert "deadlock retry strategy chosen" in out
    assert "<source_data id='global/raw_source:1#0'>" in out
    assert "grocery" not in out

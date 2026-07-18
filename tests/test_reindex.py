"""Reindex: embedding-model meta guard + full vector rebuild."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.config.settings import write_default_config
from wikiforge.services import ensure_embedding_compat, run_reindex
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeEmbedder:
    dim = 4
    provider_name = "fake"

    def __init__(self, model: str = "model-a"):
        self.model = model

    async def embed(self, texts, *, kind="passage"):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


async def _wiki(tmp_path: Path):
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="T")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    return home, db, Repository(db)


async def test_compat_stamps_then_raises_on_mismatch(tmp_path: Path) -> None:
    home, db, repo = await _wiki(tmp_path)
    try:
        await ensure_embedding_compat(repo, FakeEmbedder("model-a"))
        assert await repo.get_meta("embedding_model") == "model-a"
        await ensure_embedding_compat(repo, FakeEmbedder("model-a"))  # idempotent
        with pytest.raises(ValueError, match="wiki reindex --embeddings"):
            await ensure_embedding_compat(repo, FakeEmbedder("model-b"))
    finally:
        await db.close()


async def test_run_reindex_rebuilds_all_vectors_and_meta(tmp_path: Path, monkeypatch) -> None:
    home, db, repo = await _wiki(tmp_path)
    rid = await repo.insert_chunk(
        owner_type="raw_source", owner_id=1, seq=0, text="hello", content_hash="h1"
    )
    await repo.insert_chunk_vector(rid, [9.0, 9.0, 9.0, 9.0])
    await repo.set_meta("embedding_model", "old-model")
    await db.close()

    import wikiforge.services as services

    monkeypatch.setattr(
        services, "build_embedding_provider", lambda cfg, repo, **kw: FakeEmbedder("new-model")
    )
    monkeypatch.setattr(services, "effective_embedding_dim", lambda cfg, **kw: 4)
    count = await run_reindex(home)
    assert count == 1

    db2 = await Database.open(home, dim=4)
    try:
        repo2 = Repository(db2)
        assert await repo2.get_meta("embedding_model") == "new-model"
        assert await repo2.all_chunks_missing_vectors(limit=10) == []
        row = await db2.fetchone(
            "SELECT vec_to_json(embedding) AS embedding FROM chunks_vec WHERE rowid = ?", (rid,)
        )
        assert row is not None
        import json

        assert json.loads(row["embedding"])[0] == pytest.approx(1.0)  # re-embedded, not 9.0
    finally:
        await db2.close()

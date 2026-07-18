"""Chunk index write-path: chunks + FTS + vec, with clean re-index."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.search.index import index_owner
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeEmbedder:
    def __init__(self, dim: int = 4) -> None:
        self._dim = dim

    @property
    def dim(self) -> int:
        return self._dim

    @property
    def model(self) -> str:
        return "fake"

    @property
    def provider_name(self) -> str:
        return "fake"

    async def embed(
        self, texts: list[str], *, kind: str = "passage"
    ) -> list[list[float]]:
        return [[float(len(t)), 0.0, 0.0, 0.0] for t in texts]


@pytest.fixture
async def repo(wiki_home: Path):
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    yield db, Repository(db)
    await db.close()


async def test_index_writes_chunks_fts_and_vec(repo) -> None:
    db, repository = repo
    n = await index_owner(
        repository,
        FakeEmbedder(),
        owner_type="raw_source",
        owner_id=1,
        text="# A\n\nthe quick brown fox\n\n## B\n\nlazy dog sleeps",
    )
    assert n >= 1
    rows = await db.fetchall("SELECT COUNT(*) AS c FROM chunks WHERE owner_id = 1")
    assert rows[0]["c"] == n
    fts = await db.fetchall("SELECT owner_id FROM chunks_fts WHERE chunks_fts MATCH 'quick'")
    assert len(fts) == 1
    vec = await db.fetchall("SELECT COUNT(*) AS c FROM chunks_vec")
    assert vec[0]["c"] == n


async def test_reindex_replaces_old_chunks_and_vectors(repo) -> None:
    db, repository = repo
    await index_owner(
        repository, FakeEmbedder(), owner_type="raw_source", owner_id=1, text="first version words"
    )
    await index_owner(
        repository, FakeEmbedder(), owner_type="raw_source", owner_id=1, text="second version words"
    )
    chunks = await db.fetchall("SELECT text FROM chunks WHERE owner_id = 1")
    vecs = await db.fetchall("SELECT COUNT(*) AS c FROM chunks_vec")
    assert all("first" not in r["text"] for r in chunks)  # old text gone
    assert vecs[0]["c"] == len(chunks)  # vec rows match chunk rows (no orphans)

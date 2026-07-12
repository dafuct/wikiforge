"""FTS-only indexing makes a source keyword-searchable without an embedder."""

from __future__ import annotations

from pathlib import Path

from wikiforge.search.index import index_owner_fts
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def test_index_owner_fts_populates_fts(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    home.mkdir()
    db = await Database.open(home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        n = await index_owner_fts(
            repo, owner_type="raw_source", owner_id=42,
            text="# Dev event\n\nWe fixed the retriever ranking bug.",
        )
        assert n >= 1
        rows = await db.fetchall(
            "SELECT owner_id FROM chunks_fts WHERE chunks_fts MATCH ?", ("retriever",)
        )
        assert any(r["owner_id"] == 42 for r in rows)
    finally:
        await db.close()

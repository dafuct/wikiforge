"""The schema initializes: relational tables, FTS5, and sqlite-vec all present."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.storage.db import Database

EXPECTED_TABLES = {
    "topics",
    "raw_sources",
    "articles",
    "citations",
    "conflicts",
    "research_sessions",
    "research_findings",
    "thesis_verdicts",
    "topic_links",
    "chunks",
    "inventory_items",
    "datasets",
    "activity_log",
    "feedback",
    "llm_calls",
    "embedding_cache",
}


async def _table_names(db: Database) -> set[str]:
    rows = await db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")
    return {r["name"] for r in rows}


@pytest.fixture
async def db(wiki_home: Path):
    database = await Database.open(wiki_home, dim=8)
    await database.init_schema()
    yield database
    await database.close()


async def test_all_relational_tables_created(db: Database) -> None:
    assert EXPECTED_TABLES <= await _table_names(db)


async def test_wal_mode_enabled(db: Database) -> None:
    row = await db.fetchone("PRAGMA journal_mode")
    assert row[0].lower() == "wal"


async def test_fts5_table_usable(db: Database) -> None:
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO chunks(owner_type, owner_id, seq, text, content_hash) "
            "VALUES ('article', 1, 0, 'the quick brown fox', 'h1')"
        )
        await db.conn.commit()
    rows = await db.fetchall("SELECT owner_id FROM chunks_fts WHERE chunks_fts MATCH 'quick'")
    assert len(rows) == 1


async def test_sqlite_vec_knn(db: Database) -> None:
    # dim=8 in this fixture; insert two vectors and KNN-query the nearer one.
    async with db.lock:
        await db.conn.execute(
            "INSERT INTO chunks_vec(rowid, embedding) VALUES (1, ?)",
            ("[1,0,0,0,0,0,0,0]",),
        )
        await db.conn.execute(
            "INSERT INTO chunks_vec(rowid, embedding) VALUES (2, ?)",
            ("[0,1,0,0,0,0,0,0]",),
        )
        await db.conn.commit()
    rows = await db.fetchall(
        "SELECT rowid FROM chunks_vec WHERE embedding MATCH ? AND k = 1 ORDER BY distance",
        ("[1,0,0,0,0,0,0,0]",),
    )
    assert rows[0]["rowid"] == 1


def test_citation_indexes_ddl_matches_schema_sql() -> None:
    """The DDL constant and schema.sql must stay byte-identical (single source)."""
    from wikiforge.storage.repository import CITATION_INDEXES_DDL

    schema = (
        Path(__file__).resolve().parents[1] / "wikiforge" / "storage" / "schema.sql"
    ).read_text(encoding="utf-8")
    assert CITATION_INDEXES_DDL in schema

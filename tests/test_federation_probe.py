"""Probe: can a read-only SQLite connection run FTS5 and vec0 KNN queries?

Federation opens peer wikis with ``mode=ro`` (spec §5.1). FTS5 MATCH is a
plain read and is expected to work. ``vec0`` KNN is the open question: the
extension may need scratch storage that a read-only connection denies. This
test records the observed behaviour of the installed sqlite-vec rather than
asserting a hoped-for one — whichever branch runs, the fact is pinned.
"""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import aiosqlite
import pytest
import sqlite_vec

from wikiforge.services import init_wiki
from wikiforge.storage.db import DB_FILENAME, Database


async def _build_wiki(home: Path, *, text: str, vector: list[float]) -> None:
    """Create a wiki with exactly one indexed chunk (FTS row + stored vector).

    Columns match the real schema exactly (verified against
    ``wikiforge/storage/schema.sql`` during plan review): ``raw_sources`` has
    no ``url`` column (it's ``canonical_url``, nullable) and requires
    ``content_hash`` (UNIQUE) and ``fetched_at`` (both NOT NULL, neither
    defaulted); ``chunks``' primary key column is named ``rowid`` explicitly,
    not ``id``, and it too requires ``content_hash``.
    """
    await init_wiki("probe", home)
    db = await Database.open(home, dim=len(vector))
    try:
        conn = db.conn
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
        await conn.commit()
    finally:
        await db.close()


async def _open_readonly(home: Path) -> aiosqlite.Connection:
    """Open the wiki database read-only, with sqlite-vec loaded."""
    uri = f"{(home / DB_FILENAME).resolve().as_uri()}?mode=ro"
    conn = await aiosqlite.connect(uri, uri=True)
    conn.row_factory = aiosqlite.Row
    await conn.enable_load_extension(True)
    await conn.load_extension(sqlite_vec.loadable_path())
    await conn.enable_load_extension(False)
    return conn


@pytest.mark.asyncio
async def test_readonly_connection_refuses_writes(tmp_path: Path) -> None:
    """mode=ro is the enforcement layer federation relies on (spec §5.1)."""
    home = tmp_path / "peer"
    await _build_wiki(home, text="alpha beta", vector=[0.1] * 384)
    conn = await _open_readonly(home)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly database"):
            await conn.execute("INSERT INTO wiki_meta (key, value) VALUES ('x', 'y')")
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_fts_match_works_readonly(tmp_path: Path) -> None:
    """FTS5 MATCH is a plain read and must work on a peer."""
    home = tmp_path / "peer"
    await _build_wiki(home, text="alpha beta", vector=[0.1] * 384)
    conn = await _open_readonly(home)
    try:
        async with conn.execute(
            "SELECT rowid FROM chunks_fts WHERE chunks_fts MATCH 'alpha'"
        ) as cur:
            rows = list(await cur.fetchall())
        assert [r["rowid"] for r in rows] == [1]
    finally:
        await conn.close()


@pytest.mark.asyncio
async def test_vec_knn_readonly_behaviour_is_pinned(tmp_path: Path) -> None:
    """Record whether vec0 KNN runs read-only; both outcomes are acceptable.

    Task 6's ``peer_candidates`` catches ``sqlite3.OperationalError`` and
    degrades to FTS-only, so federation is correct either way. This test
    exists so the answer is a recorded fact rather than folklore: update the
    assertion below to match what the probe actually printed, and record the
    same finding in spec §5.3.
    """
    home = tmp_path / "peer"
    await _build_wiki(home, text="alpha beta", vector=[0.1] * 384)
    conn = await _open_readonly(home)
    try:
        try:
            async with conn.execute(
                "SELECT rowid FROM chunks_vec WHERE embedding MATCH :vec ORDER BY distance LIMIT 5",
                {"vec": json.dumps([0.1] * 384)},
            ) as cur:
                rows = list(await cur.fetchall())
            observed = f"ok: {len(rows)} row(s)"
        except sqlite3.OperationalError as exc:
            observed = f"refused: {exc}"
    finally:
        await conn.close()
    print(f"\nPROBE vec0 KNN read-only → {observed}")
    # Probe printed "ok:" — pin that outcome so a future sqlite-vec regression is caught.
    assert observed.startswith("ok:"), observed

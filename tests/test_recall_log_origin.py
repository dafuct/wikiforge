"""recall_log must distinguish a peer's chunk from a local one with the same ids."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.search.rrf import ChunkTarget
from wikiforge.services import init_wiki
from wikiforge.storage.db import Database
from wikiforge.storage.repository import RECALL_LOG_DDL, Repository


def _target(rowid: int) -> ChunkTarget:
    return ChunkTarget(
        rowid=rowid,
        owner_type="article",
        owner_id=7,
        seq=2,
        text="t",
        topic_id=None,
        topic_status=None,
    )


def test_schema_and_ensure_share_one_ddl() -> None:
    """Single-source DDL, as dev_event_files and capture_watermark already are."""
    schema = (Path("wikiforge/storage/schema.sql")).read_text(encoding="utf-8")
    body = RECALL_LOG_DDL.strip().rstrip(";")
    assert body.split("(", 1)[0].strip() in schema
    assert "origin" in schema.split("recall_log", 1)[1][:400]
    # Byte-identical containment, exactly the check test_why_index.py already runs
    # for DEV_EVENT_FILES_DDL/WHY_LOG_DDL/CAPTURE_WATERMARK_DDL — the two weaker
    # asserts above would miss a drifted column type or PK order; this one can't.
    assert RECALL_LOG_DDL in schema


@pytest.mark.asyncio
async def test_peer_and_local_chunk_with_identical_ids_both_log(tmp_path: Path) -> None:
    """The collision the primary key would otherwise hide (spec §7.5)."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    db = await Database.open(home, dim=384)
    try:
        repo = Repository(db)
        await repo.ensure_recall_log()
        await repo.log_recall(
            "s1", [("", _target(1)), ("global", _target(1))], "2026-07-21T00:00:00Z"
        )
        seen = await repo.recall_seen("s1")
    finally:
        await db.close()
    assert seen == {("", "article", 7, 2), ("global", "article", 7, 2)}


@pytest.mark.asyncio
async def test_legacy_table_is_rebuilt(tmp_path: Path) -> None:
    """A pre-cycle-4 recall_log is dropped and recreated (accepted: a session
    in flight may see one excerpt twice; rows are purged after 7 days anyway)."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    db = await Database.open(home, dim=384)
    try:
        await db.conn.execute("DROP TABLE IF EXISTS recall_log")
        await db.conn.execute(
            "CREATE TABLE recall_log (session_id TEXT NOT NULL, owner_type TEXT NOT NULL,"
            " owner_id INTEGER NOT NULL, seq INTEGER NOT NULL, ts TEXT NOT NULL,"
            " PRIMARY KEY (session_id, owner_type, owner_id, seq))"
        )
        await db.conn.execute(
            "INSERT INTO recall_log VALUES ('old', 'article', 1, 0, '2026-01-01T00:00:00Z')"
        )
        await db.conn.commit()

        repo = Repository(db)
        await repo.ensure_recall_log()
        cols = {
            row["name"]
            for row in await db.fetchall("SELECT name FROM pragma_table_info('recall_log')")
        }
        await repo.ensure_recall_log()  # idempotent
    finally:
        await db.close()
    assert "origin" in cols


@pytest.mark.asyncio
async def test_ensure_is_a_noop_on_a_current_table(tmp_path: Path) -> None:
    """Re-running must not discard live dedup state."""
    home = tmp_path / "wiki"
    await init_wiki("w", home)
    db = await Database.open(home, dim=384)
    try:
        repo = Repository(db)
        await repo.ensure_recall_log()
        await repo.log_recall("s1", [("", _target(1))], "2026-07-21T00:00:00Z")
        await repo.ensure_recall_log()
        seen = await repo.recall_seen("s1")
    finally:
        await db.close()
    assert seen == {("", "article", 7, 2)}

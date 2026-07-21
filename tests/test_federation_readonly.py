"""Read-only peer access — the invariant the whole design rests on."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from wikiforge.federation.peers import (
    PeerUnavailable,
    PeerWriteAttempted,
    ReadOnlyDatabase,
)
from wikiforge.services import init_wiki
from wikiforge.storage.repository import Repository


@pytest.mark.asyncio
async def test_open_missing_database_raises_peer_unavailable(tmp_path: Path) -> None:
    """A registry entry can outlive the wiki it points at."""
    with pytest.raises(PeerUnavailable):
        await ReadOnlyDatabase.open(tmp_path / "gone", dim=384)


@pytest.mark.asyncio
async def test_open_does_not_create_anything(tmp_path: Path) -> None:
    """Opening a peer must never mkdir or create a database (Database.open does)."""
    target = tmp_path / "not-a-wiki"
    with pytest.raises(PeerUnavailable):
        await ReadOnlyDatabase.open(target, dim=384)
    assert not target.exists()


@pytest.mark.asyncio
async def test_execute_raises_before_sqlite_does(tmp_path: Path) -> None:
    """Our own fail-fast layer, covering the 3 call sites that use db.execute."""
    home = tmp_path / "peer"
    await init_wiki("peer", home)
    db = await ReadOnlyDatabase.open(home, dim=384)
    try:
        with pytest.raises(PeerWriteAttempted):
            await db.execute("INSERT INTO wiki_meta (key, value) VALUES ('a', 'b')")
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_sqlite_refuses_writes_through_the_connection(tmp_path: Path) -> None:
    """The real guarantee: mode=ro denies every write path, including raw conn
    access, which is how Repository performs most of its writes."""
    home = tmp_path / "peer"
    await init_wiki("peer", home)
    db = await ReadOnlyDatabase.open(home, dim=384)
    try:
        with pytest.raises(sqlite3.OperationalError, match="readonly database"):
            await db.conn.execute("INSERT INTO wiki_meta (key, value) VALUES ('a', 'b')")
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_repository_reads_work_against_a_peer(tmp_path: Path) -> None:
    """Repository is reused unchanged for reads (spec §5.1)."""
    home = tmp_path / "peer"
    await init_wiki("peer", home)
    db = await ReadOnlyDatabase.open(home, dim=384)
    try:
        repo = Repository(db)  # type: ignore[arg-type]
        assert await repo.get_meta("embedding_dim") == "384"
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_repository_writes_fail_against_a_peer(tmp_path: Path) -> None:
    """A Repository write method routed at a peer must fail, not silently no-op."""
    home = tmp_path / "peer"
    await init_wiki("peer", home)
    db = await ReadOnlyDatabase.open(home, dim=384)
    try:
        repo = Repository(db)  # type: ignore[arg-type]
        with pytest.raises((sqlite3.OperationalError, PeerWriteAttempted)):
            await repo.set_meta("embedding_model", "hacked")
    finally:
        await db.close()

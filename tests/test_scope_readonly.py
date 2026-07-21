"""Path lookups against a peer: never write, never raise on a missing index."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.federation.peers import ReadOnlyDatabase
from wikiforge.ops.scope import events_for_absolute, events_for_paths
from wikiforge.services import init_wiki
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def _wiki_without_file_index(home: Path) -> None:
    """A wiki as rss/nimbus are today: no dev_event_files table (spec §1.1)."""
    await init_wiki("peer", home)
    db = await Database.open(home, dim=384)
    try:
        await db.conn.execute("DROP TABLE IF EXISTS dev_event_files")
        await db.conn.commit()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_read_only_lookup_does_not_create_the_index(tmp_path: Path) -> None:
    """The ensure would be a write; a peer must be left exactly as found."""
    home = tmp_path / "peer"
    await _wiki_without_file_index(home)
    db = await ReadOnlyDatabase.open(home, dim=384)
    try:
        found = await events_for_paths(
            Repository(db),  # type: ignore[arg-type]
            ["a.py"],
            root="/repo",
            limit=5,
            read_only=True,
        )
    finally:
        await db.close()
    assert found.events == []

    check = await Database.open(home, dim=384)
    try:
        row = await check.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dev_event_files'"
        )
    finally:
        await check.close()
    assert row is None, "a peer lookup must not create dev_event_files"


@pytest.mark.asyncio
async def test_absolute_lookup_is_read_only_safe(tmp_path: Path) -> None:
    """The guardrail always supplies an absolute path; it too must degrade."""
    home = tmp_path / "peer"
    await _wiki_without_file_index(home)
    db = await ReadOnlyDatabase.open(home, dim=384)
    try:
        events = await events_for_absolute(
            Repository(db),  # type: ignore[arg-type]
            "/repo/a.py",
            limit=5,
            read_only=True,
        )
    finally:
        await db.close()
    assert events == []


@pytest.mark.asyncio
async def test_local_behaviour_is_unchanged(tmp_path: Path) -> None:
    """Default read_only=False still ensures and backfills the index."""
    home = tmp_path / "local"
    await init_wiki("local", home)
    db = await Database.open(home, dim=384)
    try:
        found = await events_for_paths(Repository(db), ["a.py"], root="", limit=5)
        assert found.events == []
        row = await db.fetchone(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='dev_event_files'"
        )
        assert row is not None
    finally:
        await db.close()

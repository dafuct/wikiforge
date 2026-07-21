"""wiki impact's file target sees peer decision history; source/topic stay local."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.federation.fanout import Sourced
from wikiforge.federation.registry import PeerRef, save_registry
from wikiforge.models.domain import RawSource
from wikiforge.ops.impact import build_file_impact
from wikiforge.services import init_wiki, run_impact
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_HASHES = iter(range(1, 10_000))


async def _wiki_with_event(home: Path, *, path: str, ts: str, summary: str) -> None:
    """A wiki holding exactly one dev event that touched ``path`` (Task 9's pattern)."""
    await init_wiki("w", home)
    db = await Database.open(home, dim=384)
    try:
        repo = Repository(db)
        await repo.ensure_dev_event_files()
        source_id, _ = await repo.ingest_raw_source(
            RawSource(
                content_hash=f"impact-fixture-{next(_HASHES)}",
                source_type="dev_event",
                title=summary,
                text=f"## Request (why)\n{summary}\n",
                fetched_at=datetime.fromisoformat(ts),
                provenance={"summary": summary},
            )
        )
        await db.conn.execute(
            "INSERT INTO dev_event_files (source_id, path) VALUES (:sid, :p)",
            {"sid": source_id, "p": path},
        )
        await db.conn.commit()
    finally:
        await db.close()


@pytest.mark.asyncio
async def test_local_only_events_are_sourced_with_empty_origin(tmp_path: Path) -> None:
    """Type change (list[RawSource] -> list[Sourced[RawSource]]) must not alter local output."""
    home = tmp_path / "local"
    await _wiki_with_event(home, path="/repo/a.py", ts="2026-07-18T10:00:00+00:00", summary="local")
    db = await Database.open(home, dim=384)
    try:
        report = await build_file_impact(Repository(db), "a.py", root="/repo", limit=10)
    finally:
        await db.close()
    events: list[Sourced[RawSource]] = report.events
    assert [s.origin for s in events] == [""]
    assert events[0].item.provenance["summary"] == "local"


@pytest.mark.asyncio
async def test_run_impact_file_target_merges_peers(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A file's blast radius includes a peer's decision history, newest first.

    Mirrors ``test_run_why_merges_peers_newest_first`` (Task 9): an absolute
    target sidesteps any dependency on this test process's own git root, and
    the peer's later timestamp must sort ahead of the local one.
    """
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path / "cfg"))
    target = "/repo/wikiforge/services.py"
    local = tmp_path / "local"
    peer = tmp_path / "peer"
    await _wiki_with_event(
        local, path=target, ts="2026-07-18T10:00:00+00:00", summary="local decision"
    )
    await _wiki_with_event(
        peer, path=target, ts="2026-07-20T10:00:00+00:00", summary="peer decision"
    )
    save_registry([PeerRef("global", peer)])

    out = await run_impact(local, target, limit=10)
    lines = out.splitlines()

    def _line_with(needle: str) -> str:
        matches = [line for line in lines if needle in line]
        assert matches, f"{needle!r} not found in:\n{out}"
        return matches[0]

    peer_line = _line_with("peer decision")
    local_line = _line_with("local decision")
    assert lines.index(peer_line) < lines.index(local_line)
    assert "[global]" in peer_line
    assert "[global]" not in local_line

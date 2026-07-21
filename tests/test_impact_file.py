"""Blast radius of a file: the decisions on it, and what historically moved with it."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.ops.impact import build_file_impact
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

pytestmark = pytest.mark.asyncio


async def _event(repo: Repository, *, title: str, files: list[str]) -> int:
    source_id, _ = await repo.ingest_raw_source(
        RawSource(
            content_hash=title, canonical_url=None, source_type=SourceType.DEV_EVENT,
            title=title, text=title,
            fetched_at=datetime.fromisoformat("2026-07-01T00:00:00+00:00"),
            provenance={"files": ",".join(files), "type": "change"},
        )
    )
    await repo.add_dev_event_files(source_id, files)
    return source_id


async def test_co_changed_files_are_ranked_by_shared_events(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        await repo.ensure_dev_event_files()
        await _event(repo, title="1", files=["/r/a.py", "/r/near.py"])
        await _event(repo, title="2", files=["/r/a.py", "/r/near.py"])
        await _event(repo, title="3", files=["/r/a.py", "/r/far.py"])

        report = await build_file_impact(repo, "a.py", root="/r", limit=10)

        assert report.co_changed == [("/r/near.py", 2), ("/r/far.py", 1)]
        assert len(report.events) == 3
    finally:
        await db.close()


async def test_co_changed_files_from_another_repo_are_filtered_out(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        await repo.ensure_dev_event_files()
        await _event(repo, title="1", files=["/r/a.py", "/other/x.py", "/r/near.py"])

        report = await build_file_impact(repo, "a.py", root="/r", limit=10)

        assert report.co_changed == [("/r/near.py", 1)]
    finally:
        await db.close()


async def test_a_file_with_no_history_reports_an_empty_radius(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        await repo.ensure_dev_event_files()

        report = await build_file_impact(repo, "ghost.py", root="/r", limit=10)

        assert report.events == [] and report.co_changed == []
    finally:
        await db.close()

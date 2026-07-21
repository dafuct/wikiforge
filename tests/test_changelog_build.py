"""Two-armed changelog selection: repo-anchored files, plus file-less by time."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.ops.changelog import Range, build_changelog
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

pytestmark = pytest.mark.asyncio

_RANGE = Range(
    base="aaaa", head="bbbb",
    base_iso="2026-07-20T00:00:00.000000+00:00",
    head_iso="2026-07-20T23:59:59.999999+00:00",
    commits=3, paths=["a.py", "b.py"],
)


async def _event(
    repo: Repository, *, title: str, files: list[str], when: str,
    kind: str = "change", provenance_extra: dict[str, str] | None = None,
) -> int:
    source_id, _ = await repo.ingest_raw_source(
        RawSource(
            content_hash=title, canonical_url=None, source_type=SourceType.DEV_EVENT,
            title=title, text=title, fetched_at=datetime.fromisoformat(when),
            provenance={"files": ",".join(files), "type": kind, **(provenance_extra or {})},
        )
    )
    if files:
        await repo.add_dev_event_files(source_id, files)
    return source_id


async def _repo(home: Path) -> tuple[Database, Repository]:
    db = await Database.open(home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    await repo.ensure_dev_event_files()
    return db, repo


async def test_file_arm_selects_events_under_the_repo_root(wiki_home: Path) -> None:
    db, repo = await _repo(wiki_home)
    try:
        mine = await _event(repo, title="mine", files=["/r/a.py"], when="2026-07-20T10:00:00+00:00")
        await _event(repo, title="theirs", files=["/other/a.py"], when="2026-07-20T10:00:00+00:00")

        log = await build_changelog(repo, _RANGE, root="/r", limit=50, exclude_types=frozenset())

        assert [e.event.id for e in log.entries] == [mine]
        assert log.entries[0].matched_by == "files"
        assert log.files_with_history == 1
    finally:
        await db.close()


async def test_window_arm_picks_up_file_less_decisions(wiki_home: Path) -> None:
    db, repo = await _repo(wiki_home)
    try:
        bare = await _event(repo, title="design", files=[], when="2026-07-20T12:00:00+00:00")
        await _event(repo, title="too-early", files=[], when="2026-07-19T12:00:00+00:00")

        log = await build_changelog(repo, _RANGE, root="/r", limit=50, exclude_types=frozenset())

        assert [e.event.id for e in log.entries] == [bare]
        assert log.entries[0].matched_by == "window"
    finally:
        await db.close()


async def test_file_less_events_from_another_repo_are_dropped(wiki_home: Path) -> None:
    db, repo = await _repo(wiki_home)
    try:
        await _event(repo, title="elsewhere", files=[], when="2026-07-20T12:00:00+00:00",
                     provenance_extra={"repo": "/other"})

        log = await build_changelog(repo, _RANGE, root="/r", limit=50, exclude_types=frozenset())

        assert log.entries == []
    finally:
        await db.close()


async def test_file_less_events_with_no_repo_key_are_kept(wiki_home: Path) -> None:
    """Unknown means unknown, not mismatched — every pre-F0 event lacks the key."""
    db, repo = await _repo(wiki_home)
    try:
        legacy = await _event(repo, title="legacy", files=[], when="2026-07-20T12:00:00+00:00")

        log = await build_changelog(repo, _RANGE, root="/r", limit=50, exclude_types=frozenset())

        assert [e.event.id for e in log.entries] == [legacy]
    finally:
        await db.close()


async def test_an_event_matched_by_both_arms_appears_once_as_files(wiki_home: Path) -> None:
    db, repo = await _repo(wiki_home)
    try:
        both = await _event(repo, title="both", files=["/r/a.py"], when="2026-07-20T12:00:00+00:00")

        log = await build_changelog(repo, _RANGE, root="/r", limit=50, exclude_types=frozenset())

        assert [(e.event.id, e.matched_by) for e in log.entries] == [(both, "files")]
    finally:
        await db.close()


async def test_excluded_types_are_dropped_and_counted(wiki_home: Path) -> None:
    db, repo = await _repo(wiki_home)
    try:
        kept = await _event(repo, title="fix", files=["/r/a.py"],
                            when="2026-07-20T10:00:00+00:00", kind="bugfix")
        await _event(repo, title="noise", files=["/r/b.py"],
                     when="2026-07-20T11:00:00+00:00", kind="chore")

        log = await build_changelog(repo, _RANGE, root="/r", limit=50,
                                    exclude_types=frozenset({"chore"}))

        assert [e.event.id for e in log.entries] == [kept]
        assert log.excluded == 1
    finally:
        await db.close()


async def test_entries_are_newest_first(wiki_home: Path) -> None:
    db, repo = await _repo(wiki_home)
    try:
        old = await _event(repo, title="old", files=["/r/a.py"], when="2026-07-20T08:00:00+00:00")
        new = await _event(repo, title="new", files=["/r/b.py"], when="2026-07-20T20:00:00+00:00")

        log = await build_changelog(repo, _RANGE, root="/r", limit=50, exclude_types=frozenset())

        assert [e.event.id for e in log.entries] == [new, old]
    finally:
        await db.close()

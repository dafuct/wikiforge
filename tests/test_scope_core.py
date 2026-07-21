"""The repo-scoping core: anchoring relative paths onto the absolute index.

These tests exercise the anchor-first / suffix-fallback rule and the
all-or-nothing property of the fallback. They do not test rendering or any
feature built on top — those have their own files.
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.ops.scope import anchor_paths, events_for_paths, repo_root
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

pytestmark = pytest.mark.asyncio


async def _event(repo: Repository, *, title: str, files: list[str]) -> int:
    source_id, _ = await repo.ingest_raw_source(
        RawSource(
            content_hash=title,
            canonical_url=None,
            source_type=SourceType.DEV_EVENT,
            title=title,
            text=title,
            fetched_at=datetime.fromisoformat("2026-07-01T00:00:00+00:00"),
            provenance={"files": ",".join(files), "type": "change"},
        )
    )
    await repo.add_dev_event_files(source_id, files)
    return source_id


def test_repo_root_returns_empty_when_git_fails() -> None:
    def boom(argv: list[str]) -> str:
        raise OSError("not a repo")

    assert repo_root(runner=boom) == ""


def test_repo_root_strips_trailing_newline() -> None:
    assert repo_root(runner=lambda argv: "/Users/dev/proj\n") == "/Users/dev/proj"


def test_anchor_paths_joins_onto_the_root() -> None:
    assert anchor_paths("/r", ["a.py", "sub/b.py"]) == ["/r/a.py", "/r/sub/b.py"]


def test_anchor_paths_passes_absolute_paths_through() -> None:
    assert anchor_paths("/r", ["/other/a.py"]) == ["/other/a.py"]


def test_anchor_paths_without_a_root_is_identity() -> None:
    assert anchor_paths("", ["a.py"]) == ["a.py"]


async def test_events_for_paths_prefers_the_anchored_repo(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        await repo.ensure_dev_event_files()
        mine = await _event(repo, title="mine", files=["/r/README.md"])
        await _event(repo, title="theirs", files=["/other/README.md"])

        found = await events_for_paths(repo, ["README.md"], root="/r", limit=10)

        assert [e.id for e in found.events] == [mine]
        assert found.matched == {"README.md"}
        assert found.fell_back is False
    finally:
        await db.close()


async def test_events_for_paths_falls_back_to_suffix_when_anchoring_finds_nothing(
    wiki_home: Path,
) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        await repo.ensure_dev_event_files()
        theirs = await _event(repo, title="theirs", files=["/other/README.md"])

        found = await events_for_paths(repo, ["README.md"], root="/r", limit=10)

        assert [e.id for e in found.events] == [theirs]
        assert found.matched == {"README.md"}
        assert found.fell_back is True
    finally:
        await db.close()


async def test_fallback_is_not_reported_when_it_found_nothing_either(wiki_home: Path) -> None:
    """Nothing to label: an empty result is not a cross-project answer."""
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        await repo.ensure_dev_event_files()

        found = await events_for_paths(repo, ["ghost.py"], root="/r", limit=10)

        assert found.events == [] and found.fell_back is False
    finally:
        await db.close()


async def test_no_fallback_flag_without_a_repo_root(wiki_home: Path) -> None:
    """Outside a repo there is no anchoring to fall back *from*."""
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        await repo.ensure_dev_event_files()
        theirs = await _event(repo, title="theirs", files=["/other/README.md"])

        found = await events_for_paths(repo, ["README.md"], root="", limit=10)

        assert [e.id for e in found.events] == [theirs]
        assert found.fell_back is False
    finally:
        await db.close()


async def test_fallback_is_all_or_nothing_never_per_path(wiki_home: Path) -> None:
    """A partial anchored hit must NOT be topped up with cross-project suffix hits.

    Mixing the two would silently reintroduce contamination for whichever paths
    happened to miss — the exact failure repo anchoring exists to prevent.
    """
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        await repo.ensure_dev_event_files()
        mine = await _event(repo, title="mine", files=["/r/a.py"])
        await _event(repo, title="theirs", files=["/other/b.py"])

        found = await events_for_paths(repo, ["a.py", "b.py"], root="/r", limit=10)

        assert [e.id for e in found.events] == [mine]
        assert found.matched == {"a.py"}
        assert found.fell_back is False
    finally:
        await db.close()


async def test_events_for_paths_is_empty_for_no_paths(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        found = await events_for_paths(repo, [], root="/r", limit=10)

        assert found.events == [] and found.matched == set() and found.fell_back is False
    finally:
        await db.close()

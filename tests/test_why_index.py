"""dev_event_files: ensure/backfill idempotence, suffix matching, capture writes."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.models.domain import RawSource
from wikiforge.models.enums import SourceType
from wikiforge.storage.db import Database
from wikiforge.storage.repository import DEV_EVENT_FILES_DDL, Repository

_NOW = datetime(2026, 7, 20, 9, 0, 0, tzinfo=UTC)


async def _wiki(tmp_path: Path):
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="T")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    return home, db, Repository(db), load_config(home)


async def _event(repo, files: str, ts: str, event_type: str = "bugfix") -> RawSource:
    src = RawSource(
        content_hash=f"h-{ts}-{files}", source_type=SourceType.DEV_EVENT,
        title=f"Dev event {ts}", text=f"note {files}", fetched_at=_NOW,
        provenance={"ts": ts, "type": event_type, "files": files},
    )
    await repo.ingest_raw_source(src)
    stored = await repo.get_raw_source_by_hash(src.content_hash)
    assert stored is not None
    return stored


def test_ddl_single_source_matches_schema() -> None:
    from wikiforge.storage.repository import WHY_LOG_DDL

    schema = (Path("wikiforge/storage/schema.sql")).read_text(encoding="utf-8")
    assert DEV_EVENT_FILES_DDL in schema
    assert WHY_LOG_DDL in schema


async def test_backfill_populates_once_and_is_idempotent(tmp_path: Path) -> None:
    home, db, repo, cfg = await _wiki(tmp_path)
    try:
        await _event(repo, "/repo/wikiforge/a.py,/repo/wikiforge/b.py", "2026-07-19T10:00:00Z")
        await db.conn.execute("DROP TABLE dev_event_files")  # simulate a pre-upgrade wiki
        await db.conn.commit()
        await repo.ensure_dev_event_files()
        rows = await db.fetchall("SELECT source_id, path FROM dev_event_files ORDER BY path")
        assert [r["path"] for r in rows] == ["/repo/wikiforge/a.py", "/repo/wikiforge/b.py"]

        # Prove the second call actually SKIPS the backfill scan via its early-return
        # guard — asserting only the row count stays at 2 would also pass if that
        # guard were deleted, since INSERT OR IGNORE silently absorbs re-scanned
        # duplicates. Wrap the query the backfill scan drives and assert it's never
        # invoked on the second call.
        original = repo._q.all_dev_event_provenance
        calls = 0

        def _counting_wrapper(*args: object, **kwargs: object) -> object:
            nonlocal calls
            calls += 1
            return original(*args, **kwargs)

        repo._q.all_dev_event_provenance = _counting_wrapper
        try:
            await repo.ensure_dev_event_files()  # second run: guard should short-circuit
        finally:
            repo._q.all_dev_event_provenance = original
        assert calls == 0  # backfill scan was skipped, not merely re-absorbed

        rows2 = await db.fetchall("SELECT COUNT(*) AS n FROM dev_event_files")
        assert rows2[0]["n"] == 2
    finally:
        await db.close()


async def test_path_matching_exact_and_suffix_with_false_positive_guard(tmp_path) -> None:
    home, db, repo, cfg = await _wiki(tmp_path)
    try:
        await _event(repo, "/repo/wikiforge/data.py", "2026-07-19T10:00:00Z")
        await repo.ensure_dev_event_files()
        assert await repo.dev_events_for_path("/repo/wikiforge/data.py", limit=5)  # exact
        assert await repo.dev_events_for_path("data.py", limit=5)                  # suffix
        assert await repo.dev_events_for_path("wikiforge/data.py", limit=5)        # longer suffix
        assert await repo.dev_events_for_path("a.py", limit=5) == []               # NOT a.py
    finally:
        await db.close()


async def test_underscore_and_percent_in_path_match_literally(tmp_path: Path) -> None:
    home, db, repo, cfg = await _wiki(tmp_path)
    try:
        await _event(repo, "/repo/wikiforge/test_capture.py", "2026-07-19T10:00:00Z")
        await _event(repo, "/repo/wikiforge/testXcapture.py", "2026-07-19T11:00:00Z")
        await _event(repo, "/repo/wikiforge/100%done.py", "2026-07-19T12:00:00Z")
        await _event(repo, "/repo/wikiforge/100Xdone.py", "2026-07-19T13:00:00Z")
        await repo.ensure_dev_event_files()

        # `_` is a LIKE wildcard for "any single char" — unescaped, "test_capture.py"
        # would also match "testXcapture.py". Python paths contain underscores
        # routinely, so this was an everyday false positive, not an adversarial one.
        events = await repo.dev_events_for_path("test_capture.py", limit=5)
        assert len(events) == 1
        assert events[0].provenance["files"] == "/repo/wikiforge/test_capture.py"

        # `%` is a LIKE wildcard for "any sequence" — same guarantee for a path
        # segment containing a literal percent sign.
        percent_events = await repo.dev_events_for_path("100%done.py", limit=5)
        assert len(percent_events) == 1
        assert percent_events[0].provenance["files"] == "/repo/wikiforge/100%done.py"
    finally:
        await db.close()


async def test_newest_first_and_limit(tmp_path: Path) -> None:
    home, db, repo, cfg = await _wiki(tmp_path)
    try:
        await _event(repo, "/r/x.py", "2026-07-01T10:00:00Z")
        newer = await _event(repo, "/r/x.py", "2026-07-19T10:00:00Z")
        await repo.ensure_dev_event_files()
        events = await repo.dev_events_for_path("x.py", limit=1)
        assert [e.id for e in events] == [newer.id]
    finally:
        await db.close()


async def test_capture_event_writes_index_rows(tmp_path: Path) -> None:
    from wikiforge.ops.capture import capture_event

    home, db, repo, cfg = await _wiki(tmp_path)
    try:
        src = await capture_event(
            repo, request="fix the deadlock in the bridge please", files=["/r/bridge.py"],
            event_type=None, default_type="change", origin="hook", cfg=cfg, llm=None,
            now=_NOW, git_runner=lambda argv: "",
        )
        assert src is not None
        rows = await db.fetchall("SELECT path FROM dev_event_files WHERE source_id = ?", (src.id,))
        assert [r["path"] for r in rows] == ["/r/bridge.py"]
    finally:
        await db.close()

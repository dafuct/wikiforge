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
    schema = (Path("wikiforge/storage/schema.sql")).read_text(encoding="utf-8")
    assert DEV_EVENT_FILES_DDL in schema  # one source of truth, pinned


async def test_backfill_populates_once_and_is_idempotent(tmp_path: Path) -> None:
    home, db, repo, cfg = await _wiki(tmp_path)
    try:
        await _event(repo, "/repo/wikiforge/a.py,/repo/wikiforge/b.py", "2026-07-19T10:00:00Z")
        await db.conn.execute("DROP TABLE dev_event_files")  # simulate a pre-upgrade wiki
        await db.conn.commit()
        await repo.ensure_dev_event_files()
        rows = await db.fetchall("SELECT source_id, path FROM dev_event_files ORDER BY path")
        assert [r["path"] for r in rows] == ["/repo/wikiforge/a.py", "/repo/wikiforge/b.py"]
        await repo.ensure_dev_event_files()  # second run: no dupes, no error
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

"""The watermark keeps Stop / SubagentStop / PreCompact from capturing the same turn."""

from __future__ import annotations

from pathlib import Path

from wikiforge.config.settings import write_default_config
from wikiforge.storage.db import Database
from wikiforge.storage.repository import CAPTURE_WATERMARK_DDL, Repository


async def _repo(tmp_path: Path):
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="T")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    return db, Repository(db)


def test_watermark_ddl_is_single_source() -> None:
    schema = Path("wikiforge/storage/schema.sql").read_text(encoding="utf-8")
    assert CAPTURE_WATERMARK_DDL in schema


async def test_watermark_roundtrip_and_upsert(tmp_path: Path) -> None:
    db, repo = await _repo(tmp_path)
    try:
        await repo.ensure_capture_watermark()
        assert await repo.get_watermark("s1") is None
        await repo.set_watermark("s1", "u1", "2026-07-20T10:00:00Z")
        assert await repo.get_watermark("s1") == "u1"
        await repo.set_watermark("s1", "u9", "2026-07-20T11:00:00Z")   # upsert, not duplicate
        assert await repo.get_watermark("s1") == "u9"
        assert await repo.get_watermark("s2") is None                  # per session
    finally:
        await db.close()


async def test_purge_watermarks_drops_old_rows(tmp_path: Path) -> None:
    db, repo = await _repo(tmp_path)
    try:
        await repo.ensure_capture_watermark()
        await repo.set_watermark("old", "u1", "2026-01-01T00:00:00Z")
        await repo.set_watermark("new", "u2", "2026-07-20T00:00:00Z")
        await repo.purge_watermarks("2026-07-01T00:00:00Z")
        assert await repo.get_watermark("old") is None
        assert await repo.get_watermark("new") == "u2"
    finally:
        await db.close()


async def test_ensure_is_idempotent(tmp_path: Path) -> None:
    db, repo = await _repo(tmp_path)
    try:
        await repo.ensure_capture_watermark()
        await repo.set_watermark("s1", "u1", "2026-07-20T10:00:00Z")
        await repo.ensure_capture_watermark()          # must not wipe existing rows
        assert await repo.get_watermark("s1") == "u1"
    finally:
        await db.close()

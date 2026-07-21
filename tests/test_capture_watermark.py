"""Per-surface watermarks: Stop / SubagentStop / PreCompact never re-capture a
turn they already consumed, AND — because each surface keys its mark with its
own name (``f"{session_id}:{surface}"``, see ``services._watermark_key``) —
never erase each other's progress either. The three surfaces read the same
transcript but consume COMPLEMENTARY turn sets (Stop/SubagentStop take edited
turns, PreCompact takes file-less turns), so a single shared key per session
used to mean whichever surface fired last silently blinded the others to
their own unconsumed turns.
"""

from __future__ import annotations

import json
from pathlib import Path

from wikiforge.config.settings import write_default_config
from wikiforge.services import run_capture_hook, run_capture_precompact
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


async def _init_wiki(home: Path) -> None:
    """A fully-initialized wiki home, schema created and connection closed.

    ``run_capture_hook`` opens its own ``Database`` connection against
    ``home``, so the setup connection must be closed first (mirrors
    ``tests/test_capture_service.py::_init_wiki``).
    """
    home.mkdir(parents=True, exist_ok=True)
    (home / "topics").mkdir(exist_ok=True)
    write_default_config(home, wiki_name="T")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    await db.close()


def _user_entry(uuid: str, text: str) -> dict:
    return {"type": "user", "uuid": uuid, "message": {"role": "user", "content": text}}


def _edit_entry(uuid: str, file_path: str) -> dict:
    return {
        "type": "assistant",
        "uuid": uuid,
        "message": {
            "role": "assistant",
            "content": [{"type": "tool_use", "name": "Edit", "input": {"file_path": file_path}}],
        },
    }


def _write_transcript(path: Path, entries: list[dict]) -> None:
    path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")


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


# --- run_capture_hook integration: the watermark as exercised through the hook itself ---


async def test_hook_captures_every_edited_turn_since_the_watermark(tmp_path: Path) -> None:
    """Two edited turns since the watermark must both become dev events (Finding 1).

    Under the old `edited[-1]` selection, only the SECOND turn's file
    (`/r/b.py`) would be captured and the watermark would still advance past
    both turns — silently and permanently losing the first turn's edit
    (`/r/a.py`). This test fails under that old logic; see the fix report for
    how that was verified.
    """
    home = tmp_path / "wiki"
    await _init_wiki(home)
    transcript = tmp_path / "t.jsonl"
    _write_transcript(
        transcript,
        [
            _user_entry("u1", "edit a"),
            _edit_entry("u2", "/r/a.py"),
            _user_entry("u3", "edit b"),
            _edit_entry("u4", "/r/b.py"),
        ],
    )
    stdin = json.dumps({"transcript_path": str(transcript), "session_id": "s1"})

    result = await run_capture_hook(home, stdin)
    assert result is not None

    db = await Database.open(home, dim=4)
    try:
        rows = await db.fetchall(
            "SELECT text FROM raw_sources WHERE source_type = ?", ("dev_event",)
        )
        assert len(rows) == 2  # one dev event per edited turn, not one for the whole batch
        texts = [row["text"] for row in rows]
        assert any("/r/a.py" in t for t in texts)
        assert any("/r/b.py" in t for t in texts)
    finally:
        await db.close()


async def test_hook_does_not_recapture_after_the_watermark_advances(tmp_path: Path) -> None:
    """A second hook call over the same transcript/session is a clean no-op."""
    home = tmp_path / "wiki"
    await _init_wiki(home)
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_user_entry("u1", "edit a"), _edit_entry("u2", "/r/a.py")])
    stdin = json.dumps({"transcript_path": str(transcript), "session_id": "s1"})

    first = await run_capture_hook(home, stdin)
    assert first is not None
    second = await run_capture_hook(home, stdin)
    assert second is None

    db = await Database.open(home, dim=4)
    try:
        rows = await db.fetchall(
            "SELECT text FROM raw_sources WHERE source_type = ?", ("dev_event",)
        )
        assert len(rows) == 1  # the second call created nothing additional
    finally:
        await db.close()


async def test_hook_without_session_id_does_not_touch_the_watermark(tmp_path: Path) -> None:
    """No `session_id` in the payload still captures, but never reads/writes a watermark."""
    home = tmp_path / "wiki"
    await _init_wiki(home)
    transcript = tmp_path / "t.jsonl"
    _write_transcript(transcript, [_user_entry("u1", "edit a"), _edit_entry("u2", "/r/a.py")])
    stdin = json.dumps({"transcript_path": str(transcript)})  # no session_id key at all

    result = await run_capture_hook(home, stdin)
    assert result is not None

    db = await Database.open(home, dim=4)
    try:
        rows = await db.fetchall(
            "SELECT text FROM raw_sources WHERE source_type = ?", ("dev_event",)
        )
        assert len(rows) == 1  # capture still happened

        repo = Repository(db)
        await repo.ensure_capture_watermark()  # hook never created the table either
        assert await repo.get_watermark("s1") is None
        assert await repo.get_watermark("any-other-session") is None
    finally:
        await db.close()


# --- Finding 1 (whole-branch review): per-surface keys stop Stop/PreCompact erasing
# each other's turns, since they consume COMPLEMENTARY sets from the same transcript ---


async def test_stop_capture_does_not_hide_fileless_turns_from_precompact(
    tmp_path: Path,
) -> None:
    """Stop consuming the edited turn must not blind PreCompact to the file-less
    turn that preceded it.

    Under the old shared ``session_id`` key, Stop's capture advanced the mark to
    the end of the transcript (past BOTH turns, even though Stop itself only
    ever consumes the edited one), so a later PreCompact call found nothing left
    to sweep and returned ``None`` — the file-less design discussion, the whole
    point of the PreCompact surface, was lost forever. Under the fix each
    surface keys its own mark, so PreCompact's watermark is untouched by Stop.
    """
    home = tmp_path / "wiki"
    await _init_wiki(home)
    transcript = tmp_path / "t.jsonl"
    distinctive = "discuss the frobnicator rewrite approach before committing"
    _write_transcript(
        transcript,
        [
            _user_entry("u1", distinctive),
            _user_entry("u2", "apply the auth-token fix"),
            _edit_entry("u3", "/r/auth.py"),
        ],
    )
    stdin = json.dumps({"transcript_path": str(transcript), "session_id": "s1"})

    stop_result = await run_capture_hook(home, stdin)
    assert stop_result is not None  # the edited turn was captured

    precompact_result = await run_capture_precompact(home, stdin)
    assert precompact_result is not None  # fails under the old shared key
    assert distinctive in precompact_result.text


async def test_precompact_does_not_hide_edits_from_stop(tmp_path: Path) -> None:
    """PreCompact sweeping the file-less turn must not blind Stop to the
    in-flight edited turn that follows it.

    Auto-compaction fires mid-turn by definition, so in production PreCompact's
    mark can land inside a turn that has not finished editing yet. Reproduced
    here without needing an actual mid-stream read: under the old shared
    ``session_id`` key + end-of-transcript mark, PreCompact's successful sweep
    of the file-less turn advanced the watermark past the LAST entry in the
    file — the trailing edit — even though PreCompact never consumed that
    turn. Stop's later call then found nothing after that mark and returned
    ``None``, permanently losing the edit. Under the fix, PreCompact marks only
    up to the last turn IT consumed, on ITS OWN key, so Stop's independent scan
    still finds the edited turn.
    """
    home = tmp_path / "wiki"
    await _init_wiki(home)
    transcript = tmp_path / "t.jsonl"
    _write_transcript(
        transcript,
        [
            _user_entry("u1", "discuss the frobnicator rewrite approach"),
            _user_entry("u2", "apply the auth fix"),
            _edit_entry("u3", "/r/auth_fix.py"),
        ],
    )
    stdin = json.dumps({"transcript_path": str(transcript), "session_id": "s1"})

    precompact_result = await run_capture_precompact(home, stdin)
    assert precompact_result is not None  # the file-less turn was swept

    stop_result = await run_capture_hook(home, stdin)
    assert stop_result is not None  # fails under the old shared key/mark
    assert "/r/auth_fix.py" in stop_result.text

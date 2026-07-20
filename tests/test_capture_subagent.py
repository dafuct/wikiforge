"""SubagentStop capture: subagent edits become dev events, keyed by their own session."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.ops.capture import capture_event
from wikiforge.services import run_capture_subagent
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


def _transcript(tmp_path: Path) -> Path:
    path = tmp_path / "sub.jsonl"
    rows = [
        {"uuid": "u1", "message": {"role": "user",
                                   "content": [{"type": "text", "text": "refactor the parser"}]}},
        {"uuid": "a1", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "doing it"},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/r/parser.py"}},
        ]}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


def _two_turn_transcript(tmp_path: Path) -> Path:
    """Two human turns, each editing a different file."""
    path = tmp_path / "sub_two.jsonl"
    rows = [
        {"uuid": "u1", "message": {"role": "user",
                                   "content": [{"type": "text", "text": "edit a"}]}},
        {"uuid": "a1", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/r/a.py"}},
        ]}},
        {"uuid": "u2", "message": {"role": "user",
                                   "content": [{"type": "text", "text": "edit b"}]}},
        {"uuid": "a2", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/r/b.py"}},
        ]}},
    ]
    path.write_text("\n".join(json.dumps(r) for r in rows), encoding="utf-8")
    return path


async def _home(tmp_path: Path) -> Path:
    home = tmp_path / "wiki"
    home.mkdir()
    (home / "topics").mkdir()
    write_default_config(home, wiki_name="T")
    db = await Database.open(home, dim=4)
    await db.init_schema()
    await db.close()
    return home


async def test_subagent_capture_records_files_and_origin(tmp_path: Path) -> None:
    home = await _home(tmp_path)
    payload = json.dumps({
        "session_id": "sub-1",
        "parent_session_id": "main-1",
        "transcript_path": str(_transcript(tmp_path)),
    })
    source = await run_capture_subagent(home, payload)
    assert source is not None
    assert source.provenance["origin"] == "subagent"
    assert source.provenance["parent_session_id"] == "main-1"
    assert "/r/parser.py" in source.provenance["files"]


async def test_second_call_is_deduped_by_watermark(tmp_path: Path) -> None:
    home = await _home(tmp_path)
    payload = json.dumps({
        "session_id": "sub-2", "transcript_path": str(_transcript(tmp_path)),
    })
    assert await run_capture_subagent(home, payload) is not None
    assert await run_capture_subagent(home, payload) is None      # nothing new


async def test_disabled_by_config(tmp_path: Path) -> None:
    home = await _home(tmp_path)
    cfg_path = home / "config.toml"
    cfg_path.write_text(cfg_path.read_text().replace("subagents = true", "subagents = false"))
    payload = json.dumps({
        "session_id": "sub-3", "transcript_path": str(_transcript(tmp_path)),
    })
    assert await run_capture_subagent(home, payload) is None


async def test_no_files_is_a_noop(tmp_path: Path) -> None:
    home = await _home(tmp_path)
    empty = tmp_path / "chat.jsonl"
    empty.write_text(json.dumps(
        {"uuid": "u1", "message": {"role": "user",
                                   "content": [{"type": "text", "text": "just thinking"}]}}
    ), encoding="utf-8")
    payload = json.dumps({"session_id": "sub-4", "transcript_path": str(empty)})
    assert await run_capture_subagent(home, payload) is None


async def test_subagent_captures_every_edited_turn_since_the_watermark(tmp_path: Path) -> None:
    """Two edited turns in one subagent transcript must both become dev events.

    Mirrors ``tests/test_capture_watermark.py``'s ``run_capture_hook`` regression
    test: the old ``edited[-1]`` selection would keep only the second turn's file
    while still advancing the watermark past both, permanently losing the first
    turn's edit (``/r/a.py``). ``run_capture_subagent`` must not repeat that bug.
    """
    home = await _home(tmp_path)
    payload = json.dumps({
        "session_id": "sub-two",
        "transcript_path": str(_two_turn_transcript(tmp_path)),
    })
    source = await run_capture_subagent(home, payload)
    assert source is not None

    db = await Database.open(home, dim=4)
    try:
        rows = await db.fetchall(
            "SELECT text FROM raw_sources WHERE source_type = ?", ("dev_event",)
        )
        assert len(rows) == 2  # one dev event per edited turn, not just the last
        texts = [row["text"] for row in rows]
        assert any("/r/a.py" in t for t in texts)
        assert any("/r/b.py" in t for t in texts)

        repo = Repository(db)
        assert await repo.get_watermark("sub-two") == "a2"  # advanced past both turns
    finally:
        await db.close()


async def test_extra_provenance_cannot_override_core_fields(tmp_path: Path) -> None:
    """A surface may enrich provenance but must never override what capture itself set.

    ``extra_provenance`` is spread as the BASE of the provenance dict, so any key it
    shares with capture's own core fields (``origin``, ``type``, ...) or git context
    is overwritten by the authoritative value. Non-colliding keys (like
    ``parent_session_id``) still come through untouched — enrichment still works.
    """
    home = await _home(tmp_path)
    cfg = load_config(home)
    db = await Database.open(home, dim=4)
    try:
        repo = Repository(db)
        src = await capture_event(
            repo, request="do it", files=["a.py"], event_type="feature",
            default_type="change", origin="subagent", cfg=cfg, llm=None,
            now=datetime(2026, 7, 20, 12, 0, 0, tzinfo=UTC),
            extra_provenance={
                "origin": "hijacked",
                "type": "hijacked",
                "parent_session_id": "main-9",
            },
        )
        assert src is not None
        assert src.provenance["origin"] == "subagent"     # capture's value, not "hijacked"
        assert src.provenance["type"] == "feature"         # capture's value, not "hijacked"
        assert src.provenance["parent_session_id"] == "main-9"  # enrichment still works
    finally:
        await db.close()


async def test_non_string_parent_session_id_does_not_abort_capture(tmp_path: Path) -> None:
    """A malformed (non-string) ``parent_session_id`` must be dropped, not fatal.

    ``RawSource.provenance`` is ``dict[str, str]`` on a Pydantic model; passing a
    non-string value through would raise ``pydantic.ValidationError`` inside the
    per-turn loop, which has no per-iteration try/except — aborting the whole batch
    and losing every edited turn. A bad value must be treated as "no parent
    recorded" instead.
    """
    home = await _home(tmp_path)
    payload = json.dumps({
        "session_id": "sub-5",
        "parent_session_id": 12345,  # not a string
        "transcript_path": str(_transcript(tmp_path)),
    })
    source = await run_capture_subagent(home, payload)
    assert source is not None                              # capture still succeeded
    assert not source.provenance.get("parent_session_id")  # bad value dropped, not stored

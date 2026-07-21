"""PreCompact sweeps the decisions that edited no file — the turns nothing else captures."""

from __future__ import annotations

import json
from pathlib import Path

from wikiforge.config.settings import write_default_config
from wikiforge.services import _watermark_key, run_capture_precompact
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


def _mixed_transcript(tmp_path: Path) -> Path:
    path = tmp_path / "main.jsonl"
    rows = [
        {"uuid": "u1", "message": {"role": "user", "content": [
            {"type": "text", "text": "should we use WAL or rollback journal?"}]}},
        {"uuid": "a1", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "WAL: one writer, many readers. Rejected rollback."}]}},
        {"uuid": "u2", "message": {"role": "user", "content": [
            {"type": "text", "text": "ok apply it"}]}},
        {"uuid": "a2", "message": {"role": "assistant", "content": [
            {"type": "text", "text": "editing"},
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "/r/db.py"}}]}},
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


async def test_precompact_captures_only_fileless_turns(tmp_path: Path) -> None:
    home = await _home(tmp_path)
    payload = json.dumps({"session_id": "m1", "transcript_path": str(_mixed_transcript(tmp_path))})
    source = await run_capture_precompact(home, payload)
    assert source is not None
    assert source.provenance["origin"] == "precompact"
    # The design discussion is preserved…
    assert "WAL or rollback journal" in source.text
    assert "Rejected rollback" in source.text
    # …and the file-editing turn is left to the Stop hook.
    assert "ok apply it" not in source.text


async def test_precompact_is_a_noop_when_nothing_new(tmp_path: Path) -> None:
    home = await _home(tmp_path)
    payload = json.dumps({"session_id": "m2", "transcript_path": str(_mixed_transcript(tmp_path))})
    assert await run_capture_precompact(home, payload) is not None
    assert await run_capture_precompact(home, payload) is None


async def test_precompact_respects_the_char_cap(tmp_path: Path) -> None:
    """A small cap must actually cut content, not just bound the wrapped note's length.

    ``len(source.text) < 2000`` (the brief's original assertion) passes even if the
    cap is completely broken, since the rendered note is ~300 chars regardless of
    ``precompact_max_chars``. This asserts the payload itself was truncated: the
    first (fileless) turn's request survives, but the tail of its own assistant
    prose — "Rejected rollback." — is sliced off past the 60-char cap. With the
    fixture's 93-char pre-cap payload, a cap of 60 lands mid-assistant-text (see
    the module docstring math), so this genuinely fails if truncation regresses to
    a no-op.
    """
    home = await _home(tmp_path)
    cfg_path = home / "config.toml"
    cfg_path.write_text(
        cfg_path.read_text().replace("precompact_max_chars = 20000", "precompact_max_chars = 60")
    )
    payload = json.dumps({"session_id": "m3", "transcript_path": str(_mixed_transcript(tmp_path))})
    source = await run_capture_precompact(home, payload)
    assert source is not None
    assert "should we use WAL or rollback journal?" in source.text  # survives the cap
    assert "Rejected rollback" not in source.text                   # sliced off by the cap


async def test_precompact_disabled_by_config(tmp_path: Path) -> None:
    home = await _home(tmp_path)
    cfg_path = home / "config.toml"
    cfg_path.write_text(cfg_path.read_text().replace("precompact = true", "precompact = false"))
    payload = json.dumps({"session_id": "m4", "transcript_path": str(_mixed_transcript(tmp_path))})
    assert await run_capture_precompact(home, payload) is None


async def test_precompact_does_not_advance_watermark_when_nothing_is_persisted(
    tmp_path: Path, monkeypatch
) -> None:
    """A ``capture_event`` that persists nothing must not advance the watermark.

    Mirrors the Task 5/6 correction: ``run_capture_hook``/``run_capture_subagent``
    only advance their watermark when ``capture_event`` actually returned a
    source. Advancing regardless of that would let a transient persistence
    failure permanently discard the fileless turns it never saved — the next
    PreCompact sweep only looks at turns *since* the watermark.
    """
    import wikiforge.ops.capture as capture_mod

    home = await _home(tmp_path)
    session_id = "m5"
    payload = json.dumps(
        {"session_id": session_id, "transcript_path": str(_mixed_transcript(tmp_path))}
    )

    async def _nothing_persisted(*_args: object, **_kwargs: object) -> None:
        return None

    monkeypatch.setattr(capture_mod, "capture_event", _nothing_persisted)
    assert await run_capture_precompact(home, payload) is None

    db = await Database.open(home, dim=4)
    try:
        repo = Repository(db)
        await repo.ensure_capture_watermark()
        assert await repo.get_watermark(_watermark_key(session_id, "precompact")) is None
    finally:
        await db.close()

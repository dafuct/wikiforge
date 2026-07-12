"""Service wrappers: home resolution, hook path, note path, no-op guards."""

from __future__ import annotations

import json
from pathlib import Path

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.paths import resolve_capture_home
from wikiforge.services import run_capture_hook, run_capture_note
from wikiforge.storage.db import Database


async def _init_wiki(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "topics").mkdir(exist_ok=True)
    write_default_config(home, wiki_name="Test")
    # Disable LLM summarization so these wrapper tests never make a network call.
    cfg_file = home / "config.toml"
    cfg_file.write_text(
        cfg_file.read_text(encoding="utf-8").replace("summarize = true", "summarize = false"),
        encoding="utf-8",
    )
    load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    await db.close()


def test_resolve_capture_home_prefers_local(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".wikiforge").mkdir()
    assert resolve_capture_home(None) == tmp_path / ".wikiforge"


def test_resolve_capture_home_explicit_wins(tmp_path: Path) -> None:
    assert resolve_capture_home(str(tmp_path / "w")) == tmp_path / "w"


async def test_run_capture_note_writes_event(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    await _init_wiki(home)
    src = await run_capture_note(home, "looked into RRF fusion", event_type="research")
    assert src is not None
    assert src.title.endswith("— research")


async def test_run_capture_note_no_wiki_is_noop(tmp_path: Path) -> None:
    assert await run_capture_note(tmp_path / "absent", "x", event_type=None) is None


async def test_run_capture_hook_captures_edited_turn(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    await _init_wiki(home)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "fix the bug"}})
        + "\n"
        + json.dumps({"type": "assistant", "message": {"role": "assistant", "content": [
            {"type": "tool_use", "name": "Edit", "input": {"file_path": "a.py"}}]}})
        + "\n",
        encoding="utf-8",
    )
    stdin = json.dumps({"transcript_path": str(transcript), "cwd": str(tmp_path)})
    src = await run_capture_hook(home, stdin)
    assert src is not None
    assert "a.py" in src.text


async def test_run_capture_hook_no_edits_is_noop(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    await _init_wiki(home)
    transcript = tmp_path / "t.jsonl"
    transcript.write_text(
        json.dumps({"type": "user", "message": {"role": "user", "content": "what is x?"}}) + "\n",
        encoding="utf-8",
    )
    stdin = json.dumps({"transcript_path": str(transcript)})
    assert await run_capture_hook(home, stdin) is None


async def test_run_capture_hook_auto_disabled_is_noop(tmp_path: Path) -> None:
    home = tmp_path / "wiki"
    await _init_wiki(home)
    # Rewrite config with auto = false.
    text = (home / "config.toml").read_text(encoding="utf-8").replace(
        "auto = true", "auto = false"
    )
    (home / "config.toml").write_text(text, encoding="utf-8")
    stdin = json.dumps({"transcript_path": "/does/not/matter"})
    assert await run_capture_hook(home, stdin) is None

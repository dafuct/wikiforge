"""The plugin wires a Stop hook and a wiki-note command for capture."""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_stop_hook_registered() -> None:
    hooks = json.loads((ROOT / "hooks" / "hooks.json").read_text(encoding="utf-8"))
    stop = hooks["hooks"]["Stop"]
    commands = [h["command"] for group in stop for h in group["hooks"]]
    assert any("wiki capture --hook" in c for c in commands)
    # Guarded so a missing CLI can never break the session.
    assert all("command -v wiki" in c for c in commands)
    assert all(c.rstrip().endswith("; true") for c in commands)


def test_wiki_note_command_exists() -> None:
    body = (ROOT / "commands" / "wiki-note.md").read_text(encoding="utf-8")
    assert "wiki capture --note" in body
    assert "$ARGUMENTS" in body


def _hooks() -> dict:
    return json.loads(Path("hooks/hooks.json").read_text(encoding="utf-8"))["hooks"]


def test_user_prompt_submit_hook_wired() -> None:
    hooks = _hooks()
    entries = hooks["UserPromptSubmit"][0]["hooks"]
    assert any("wiki recall --hook" in h["command"] for h in entries)
    assert all(h["command"].rstrip().endswith("true") for h in entries)  # fail-safe
    assert entries[0].get("timeout") == 15


def test_session_start_flushes_devlog_vectors() -> None:
    hooks = _hooks()
    commands = [h["command"] for h in hooks["SessionStart"][0]["hooks"]]
    assert any("wiki capture --flush" in c for c in commands)
    assert all(c.rstrip().endswith("true") for c in commands)

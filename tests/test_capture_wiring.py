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


def test_wiki_note_command_exists() -> None:
    body = (ROOT / "commands" / "wiki-note.md").read_text(encoding="utf-8")
    assert "wiki capture --note" in body
    assert "$ARGUMENTS" in body

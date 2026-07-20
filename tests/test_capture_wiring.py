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


def test_session_start_reinstalls_stale_cli() -> None:
    """SessionStart must self-heal a STALE `wiki`, not just a missing one.

    The original `command -v wiki || uv tool install` only installed when `wiki` was
    absent, so an older installed CLI (lacking newly-added commands like `recall`)
    survived forever and the hooks silently no-op'd behind `; true`.
    """
    install = _hooks()["SessionStart"][0]["hooks"][0]["command"]
    assert "-newer" in install  # staleness probe: any source .py newer than the binary
    assert "--force" in install  # and a real reinstall when stale
    # `--reinstall` and `--no-cache` are load-bearing, NOT redundant with `--force`.
    # A release bumps the package version, which uv treats as a new package and rebuilds
    # cleanly — that is the primary update path. But WITHIN a version (dev iterations, or
    # a plugin update that forgot to bump), `uv tool install --force` alone happily reuses
    # its CACHED wheel and reports success while installing the OLD code (verified live
    # 2026-07-15 and 2026-07-18). `--reinstall --no-cache` forces a fresh build from the
    # updated source so a same-version source change still lands.
    assert "--reinstall" in install
    assert "--no-cache" in install
    assert install.rstrip().endswith("true")  # still fail-safe


def test_pretooluse_guardrail_wired() -> None:
    hooks = _hooks()
    entries = hooks["PreToolUse"][0]
    assert entries["matcher"] == "Edit|Write|MultiEdit|NotebookEdit"
    commands = [h["command"] for h in entries["hooks"]]
    assert any("wiki why --hook" in c for c in commands)
    assert all("command -v wiki" in c for c in commands)
    assert all(c.rstrip().endswith("; true") for c in commands)


def test_subagent_stop_hook_wired() -> None:
    hooks = _hooks()
    commands = [h["command"] for group in hooks["SubagentStop"] for h in group["hooks"]]
    assert any("wiki capture --subagent" in c for c in commands)
    assert all("command -v wiki" in c for c in commands)
    assert all(c.rstrip().endswith("; true") for c in commands)


def test_precompact_hook_wired() -> None:
    hooks = _hooks()
    commands = [h["command"] for group in hooks["PreCompact"] for h in group["hooks"]]
    assert any("wiki capture --precompact" in c for c in commands)
    assert all("command -v wiki" in c for c in commands)
    assert all(c.rstrip().endswith("; true") for c in commands)

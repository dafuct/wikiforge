"""CLI smoke tests for `wiki capture` (manual note + hook mode)."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from wikiforge.cli.app import app
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.storage.db import Database

runner = CliRunner()


async def _init_wiki(home: Path) -> None:
    home.mkdir(parents=True, exist_ok=True)
    (home / "topics").mkdir(exist_ok=True)
    write_default_config(home, wiki_name="Test")
    # Disable LLM summarization so the CLI smoke test never makes a network call.
    cfg_file = home / "config.toml"
    cfg_file.write_text(
        cfg_file.read_text(encoding="utf-8").replace("summarize = true", "summarize = false"),
        encoding="utf-8",
    )
    load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    await db.close()


def test_capture_note(tmp_path: Path) -> None:
    import asyncio

    home = tmp_path / "wiki"
    asyncio.run(_init_wiki(home))
    result = runner.invoke(
        app, ["capture", "--home", str(home), "--note", "chose RRF over weighted sum",
               "--type", "design"],
    )
    assert result.exit_code == 0
    assert "Captured dev event" in result.stdout


def test_capture_requires_note_or_hook(tmp_path: Path) -> None:
    result = runner.invoke(app, ["capture", "--home", str(tmp_path)])
    assert result.exit_code == 1
    assert "provide --note" in result.stdout


def test_capture_hook_never_fails_without_wiki(tmp_path: Path) -> None:
    stdin = json.dumps({"transcript_path": str(tmp_path / "none.jsonl")})
    result = runner.invoke(app, ["capture", "--home", str(tmp_path), "--hook"], input=stdin)
    assert result.exit_code == 0  # exit 0 even with no wiki / no transcript

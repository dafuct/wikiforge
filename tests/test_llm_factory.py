"""build_llm_provider selects the backend from [llm] backend."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.activity.cost import CostTracker
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.anthropic_provider import AnthropicProvider
from wikiforge.llm.claude_code_provider import ClaudeCodeProvider
from wikiforge.llm.factory import build_llm_provider
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def _tracker(home: Path) -> tuple[CostTracker, Database]:
    db = await Database.open(home, dim=4)
    await db.init_schema()
    return CostTracker(Repository(db), load_config(home)), db


async def test_api_backend_builds_anthropic(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)  # default backend = api
    tracker, db = await _tracker(wiki_home)
    try:
        assert isinstance(build_llm_provider(cfg, tracker), AnthropicProvider)
    finally:
        await db.close()


async def test_subscription_backend_builds_claude_code(wiki_home: Path, monkeypatch) -> None:
    write_default_config(wiki_home, wiki_name="x")
    (wiki_home / "config.toml").write_text(
        (wiki_home / "config.toml")
        .read_text()
        .replace('backend = "api"', 'backend = "subscription"'),
        encoding="utf-8",
    )
    cfg = load_config(wiki_home)
    tracker, db = await _tracker(wiki_home)
    monkeypatch.setattr("wikiforge.llm.factory.shutil.which", lambda _: "/usr/local/bin/claude")
    try:
        assert isinstance(build_llm_provider(cfg, tracker), ClaudeCodeProvider)
    finally:
        await db.close()


async def test_subscription_without_claude_errors(wiki_home: Path, monkeypatch) -> None:
    write_default_config(wiki_home, wiki_name="x")
    (wiki_home / "config.toml").write_text(
        (wiki_home / "config.toml")
        .read_text()
        .replace('backend = "api"', 'backend = "subscription"'),
        encoding="utf-8",
    )
    cfg = load_config(wiki_home)
    tracker, db = await _tracker(wiki_home)
    monkeypatch.setattr("wikiforge.llm.factory.shutil.which", lambda _: None)
    try:
        with pytest.raises(ValueError, match="claude"):
            build_llm_provider(cfg, tracker)
    finally:
        await db.close()

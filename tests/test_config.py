"""Tests for wiki-home resolution and config loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.config.settings import Config, load_config, write_default_config
from wikiforge.paths import resolve_home


def test_resolve_home_prefers_explicit(tmp_path: Path) -> None:
    assert resolve_home(tmp_path / "here") == (tmp_path / "here")


def test_resolve_home_uses_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("WIKIFORGE_HOME", str(tmp_path / "env-home"))
    assert resolve_home(None) == (tmp_path / "env-home")


def test_resolve_home_defaults_to_user_wiki(monkeypatch) -> None:
    monkeypatch.delenv("WIKIFORGE_HOME", raising=False)
    assert resolve_home(None) == (Path.home() / "wiki")


def test_write_and_load_default_config(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="my-brain")
    cfg = load_config(wiki_home)
    assert isinstance(cfg, Config)
    assert cfg.wiki_name == "my-brain"
    assert cfg.models.cheap == "claude-haiku-4-5"
    assert cfg.models.flagship == "claude-sonnet-5"
    assert cfg.web_search.tool_version == "web_search_20260209"
    assert cfg.volatility.MEDIUM == 90
    assert cfg.embedding.dim == 1024
    assert cfg.retrieval.rrf_k == 60
    assert cfg.research.standard_personas == [
        "academic",
        "technical",
        "applied",
        "news",
        "contrarian",
    ]


def test_model_for_task_resolves_tier(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    assert cfg.model_for_task("research") == "claude-sonnet-5"
    assert cfg.model_for_task("extract") == "claude-haiku-4-5"


def test_model_for_task_tier_override(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    assert cfg.model_for_task("normalize") == "claude-haiku-4-5"  # map -> cheap
    assert cfg.model_for_task("normalize", tier="flagship") == "claude-sonnet-5"  # override wins
    assert cfg.model_for_task("research", tier="cheap") == "claude-haiku-4-5"  # override wins


def test_personas_for_mode(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    assert len(cfg.personas_for_mode("standard")) == 5
    assert len(cfg.personas_for_mode("deep")) == 8
    assert len(cfg.personas_for_mode("max")) == 10


def _cfg(tmp_path) -> Config:
    write_default_config(tmp_path, wiki_name="T")
    return load_config(tmp_path)


def test_reasoning_tier_resolves_and_unknown_tier_raises(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    assert cfg.models.reasoning == "claude-opus-4-8"
    cfg.models.tasks["thesis"] = "reasoning"
    assert cfg.model_for_task("thesis") == "claude-opus-4-8"
    assert cfg.model_for_task("thesis", tier="cheap") == cfg.models.cheap  # override still wins
    cfg.models.tasks["thesis"] = "banana"
    with pytest.raises(ValueError, match="unknown model tier"):
        cfg.model_for_task("thesis")


def test_reasoning_tier_without_model_raises(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    cfg = cfg.model_copy(update={"models": cfg.models.model_copy(update={"reasoning": None})})
    cfg.models.tasks["thesis"] = "reasoning"
    with pytest.raises(ValueError, match="reasoning"):
        cfg.model_for_task("thesis")


def test_effort_for_task_defaults_low_with_template_overrides(tmp_path) -> None:
    cfg = _cfg(tmp_path)
    assert cfg.effort_for_task("capture") == "low"
    assert cfg.effort_for_task("compile") == "low"      # MUST stay low (timeout fix)
    assert cfg.effort_for_task("thesis") == "medium"
    assert cfg.effort_for_task("synthesize") == "medium"


def test_subprocess_timeout_default(tmp_path) -> None:
    assert _cfg(tmp_path).llm.subprocess_timeout_s == 300.0

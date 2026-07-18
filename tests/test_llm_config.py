"""[llm] backend config: default is api, subscription parses, junk is rejected."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.models.enums import LlmBackend


def test_default_backend_is_api(wiki_home: Path) -> None:
    # A default config written by `wiki init` has no need to set backend explicitly.
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    assert cfg.llm.backend is LlmBackend.API


def test_config_without_llm_section_defaults_to_api(wiki_home: Path) -> None:
    # Simulate a pre-existing config.toml that predates the [llm] section entirely.
    write_default_config(wiki_home, wiki_name="x")
    text = (wiki_home / "config.toml").read_text(encoding="utf-8")
    stripped = "\n".join(
        line
        for line in text.splitlines()
        if not line.startswith(("[llm]", "backend =", "subprocess_timeout_s"))
    )
    (wiki_home / "config.toml").write_text(stripped, encoding="utf-8")
    cfg = load_config(wiki_home)
    assert cfg.llm.backend is LlmBackend.API


def test_subscription_backend_parses(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    text = (wiki_home / "config.toml").read_text(encoding="utf-8")
    (wiki_home / "config.toml").write_text(
        text.replace('backend = "api"', 'backend = "subscription"'), encoding="utf-8"
    )
    cfg = load_config(wiki_home)
    assert cfg.llm.backend is LlmBackend.SUBSCRIPTION


def test_unknown_backend_is_rejected(wiki_home: Path) -> None:
    write_default_config(wiki_home, wiki_name="x")
    text = (wiki_home / "config.toml").read_text(encoding="utf-8")
    (wiki_home / "config.toml").write_text(
        text.replace('backend = "api"', 'backend = "bogus"'), encoding="utf-8"
    )
    with pytest.raises(ValueError):
        load_config(wiki_home)

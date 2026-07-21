"""The [federation] and [maintain] config blocks, and legacy compatibility."""

from __future__ import annotations

from pathlib import Path

from wikiforge.config.defaults import DEFAULT_CONFIG_TOML
from wikiforge.config.settings import Config, load_config, write_default_config


def test_defaults_apply_when_blocks_are_absent(tmp_path: Path) -> None:
    """A config.toml written before cycle 4 keeps loading, with new defaults."""
    home = tmp_path / "wiki"
    write_default_config(home, wiki_name="legacy")
    text = (home / "config.toml").read_text(encoding="utf-8")
    stripped = text.split("[federation]")[0].split("[maintain]")[0]
    (home / "config.toml").write_text(stripped, encoding="utf-8")

    cfg = load_config(home)

    assert cfg.federation.enabled is True
    assert cfg.federation.peer_timeout_ms == 500
    assert cfg.maintain.enabled is True
    assert cfg.maintain.window_hours == 24
    assert cfg.maintain.max_calls_24h == 8
    assert cfg.maintain.max_usd_24h == 0.50
    assert cfg.maintain.jobs == ["vectors", "paths", "peers", "digests", "consolidate"]


def test_default_template_carries_both_blocks(tmp_path: Path) -> None:
    """`wiki init` writes the new blocks so they are discoverable, not hidden."""
    home = tmp_path / "wiki"
    write_default_config(home, wiki_name="fresh")
    cfg = load_config(home)
    assert "[federation]" in DEFAULT_CONFIG_TOML
    assert "[maintain]" in DEFAULT_CONFIG_TOML
    assert cfg.federation.enabled is True
    assert cfg.maintain.jobs[0] == "vectors"


def test_values_override_defaults() -> None:
    """Explicit values win, including turning federation off entirely."""
    cfg = Config.model_validate(
        {
            **_minimal_config(),
            "federation": {"enabled": False, "peer_timeout_ms": 100},
            "maintain": {"max_calls_24h": 0, "jobs": ["vectors"]},
        }
    )
    assert cfg.federation.enabled is False
    assert cfg.federation.peer_timeout_ms == 100
    assert cfg.maintain.max_calls_24h == 0
    assert cfg.maintain.jobs == ["vectors"]


def _minimal_config() -> dict[str, object]:
    """The smallest valid config payload (mirrors tests/test_config.py)."""
    return {
        "wiki_name": "t",
        "models": {"cheap": "c", "flagship": "f"},
        "pricing": {},
        "web_search": {"tool_version": "v", "max_uses": 1},
        "volatility": {"LOW": 365, "MEDIUM": 90, "HIGH": 14},
        "embedding": {
            "provider": "auto",
            "voyage_model": "v",
            "local_model": "l",
            "dim": 1024,
            "local_dim": 384,
        },
        "retrieval": {
            "rrf_k": 60,
            "top_k": 12,
            "chunk_tokens": 512,
            "chunk_overlap": 64,
            "rerank_model": "r",
        },
        "research": {"standard_personas": [], "deep_extra": [], "max_extra": []},
        "confidence": {
            "count_target": 8,
            "div_target": 6,
            "w_count": 0.35,
            "w_diversity": 0.25,
            "w_recency": 0.25,
            "w_evidence": 0.15,
            "conflict_penalty_per": 0.1,
            "conflict_penalty_cap": 0.4,
        },
    }

"""Confidence scoring: more/diverse/recent sources raise it; conflicts depress it."""

from __future__ import annotations

from pathlib import Path

from wikiforge.compile.confidence import compute_confidence
from wikiforge.config.settings import load_config, write_default_config


def _cfg(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    return load_config(wiki_home)


def test_strong_evidence_scores_high(wiki_home: Path) -> None:
    cfg = _cfg(wiki_home)
    score = compute_confidence(
        n_sources=8,
        distinct_domains=6,
        distinct_personas=5,
        median_age_days=10,
        stale_after_days=365,
        n_conflicts=0,
        evidence_strength=0.9,
        config=cfg,
    )
    assert score > 0.8


def test_conflicts_depress_confidence(wiki_home: Path) -> None:
    cfg = _cfg(wiki_home)
    base = dict(
        n_sources=8,
        distinct_domains=6,
        distinct_personas=5,
        median_age_days=10,
        stale_after_days=365,
        evidence_strength=0.9,
        config=cfg,
    )
    clean = compute_confidence(n_conflicts=0, **base)
    contested = compute_confidence(n_conflicts=3, **base)
    assert contested < clean
    assert 0.0 <= contested <= 1.0


def test_few_stale_sources_score_low(wiki_home: Path) -> None:
    cfg = _cfg(wiki_home)
    score = compute_confidence(
        n_sources=1,
        distinct_domains=1,
        distinct_personas=1,
        median_age_days=400,
        stale_after_days=90,
        n_conflicts=0,
        evidence_strength=0.2,
        config=cfg,
    )
    assert score < 0.4

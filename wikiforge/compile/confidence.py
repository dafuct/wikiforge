"""Evidence-based confidence scoring (computed in code, not by the model)."""

from __future__ import annotations

import math

from wikiforge.config.settings import Config


def compute_confidence(
    *,
    n_sources: int,
    distinct_domains: int,
    distinct_personas: int,
    median_age_days: float,
    stale_after_days: int,
    n_conflicts: int,
    evidence_strength: float,
    config: Config,
) -> float:
    """Return a confidence score in [0,1] from evidence signals (spec §9.2).

    Combines source count, source diversity (distinct domains + personas), recency
    (age vs the topic's staleness window), and model-reported evidence strength,
    minus a capped penalty for detected conflicts. Weights/targets are config-tunable.
    """
    c = config.confidence
    count_score = min(1.0, math.log1p(n_sources) / math.log1p(c.count_target))
    diversity_score = min(1.0, (distinct_domains + distinct_personas) / c.div_target)
    recency_score = 1.0 - _clamp(median_age_days / stale_after_days, 0.0, 1.0)
    conflict_penalty = min(c.conflict_penalty_cap, c.conflict_penalty_per * n_conflicts)

    raw = (
        c.w_count * count_score
        + c.w_diversity * diversity_score
        + c.w_recency * recency_score
        + c.w_evidence * _clamp(evidence_strength, 0.0, 1.0)
    )
    return round(_clamp(raw - conflict_penalty, 0.0, 1.0), 4)


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))

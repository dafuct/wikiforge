"""Reciprocal Rank Fusion (RRF) and the resolved-chunk target type."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class ChunkTarget:
    """A retrieved chunk resolved to its owner and (if any) topic."""

    rowid: int
    owner_type: str
    owner_id: int
    seq: int
    text: str
    topic_id: int | None
    topic_status: str | None
    owner_ts: str | None = None
    owner_source_type: str | None = None
    consolidated: str | None = None
    article_confidence: float | None = None
    topic_volatility: str | None = None
    topic_last_researched_at: str | None = None
    owner_event_type: str | None = None


def reciprocal_rank_fusion(
    ranked_lists: list[list[int]], *, k: int = 60
) -> list[tuple[int, float]]:
    """Merge ranked id lists with Reciprocal Rank Fusion.

    Each id's fused score is ``sum(1 / (k + rank))`` over every list it appears in,
    where ``rank`` is its 0-based position in that list. Returns ``(id, score)``
    pairs sorted by descending score; ids appearing in more (and earlier) lists
    rank higher. Ties keep first-seen order for determinism.
    """
    scores: dict[int, float] = {}
    order: list[int] = []
    for ranked in ranked_lists:
        for rank, item in enumerate(ranked):
            if item not in scores:
                scores[item] = 0.0
                order.append(item)
            scores[item] += 1.0 / (k + rank)
    position = {item: idx for idx, item in enumerate(order)}
    ranked_ids = sorted(order, key=lambda i: (-scores[i], position[i]))
    return [(i, scores[i]) for i in ranked_ids]

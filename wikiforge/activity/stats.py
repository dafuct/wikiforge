"""Aggregate wiki-wide counts and cost totals for `wiki stats`."""

from __future__ import annotations

from dataclasses import dataclass

from wikiforge.storage.repository import Repository


@dataclass(frozen=True)
class WikiStats:
    """A snapshot of wiki size and spend, optionally with a ``since`` cost window."""

    topics: int
    articles: int
    raw_sources: int
    sessions: int
    total_cost_usd: float
    cost_by_model: dict[str, float]
    since: str | None = None
    calls_since: int | None = None
    cost_since_usd: float | None = None


class StatsService:
    """Computes a :class:`WikiStats` snapshot from the repository."""

    def __init__(self, repo: Repository) -> None:
        self._repo = repo

    async def compute(self, *, since: str | None = None) -> WikiStats:
        """Aggregate entity counts and cost totals, plus a since-window when given.

        ``since`` is an ISO date (``YYYY-MM-DD``); when set, ``calls_since`` and
        ``cost_since_usd`` cover LLM calls at or after that date. When ``since``
        is ``None`` those windowed fields are ``None`` and only all-time totals
        are reported.
        """
        counts = await self._repo.entity_counts()
        cost_by_model = await self._repo.cost_totals_by_model()
        total = round(sum(cost_by_model.values()), 6)
        calls_since: int | None = None
        cost_since: float | None = None
        if since is not None:
            calls_since, cost_since = await self._repo.cost_and_calls_since(since)
            cost_since = round(cost_since, 6)
        return WikiStats(
            topics=counts["topics"],
            articles=counts["articles"],
            raw_sources=counts["raw_sources"],
            sessions=counts["sessions"],
            total_cost_usd=total,
            cost_by_model=cost_by_model,
            since=since,
            calls_since=calls_since,
            cost_since_usd=cost_since,
        )

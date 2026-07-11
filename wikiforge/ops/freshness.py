"""Topic freshness: staleness detection and triggered re-research."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from wikiforge.models.domain import Topic
from wikiforge.storage.repository import Repository


class ResearchRunner(Protocol):
    """The subset of :class:`~wikiforge.research.orchestrator.ResearchOrchestrator` used here.

    A narrow structural type (rather than the concrete orchestrator) so tests
    can inject a trivial fake that records calls instead of hitting the network.
    """

    async def research(self, *, topic_id: int, topic_title: str, mode: str) -> object:
        """Run (or resume) research for a topic; the return value is unused here."""
        ...


async def stale_topics(repo: Repository, *, now: datetime) -> list[Topic]:
    """Return ACTIVE topics whose freshness window has lapsed as of ``now``.

    A topic is stale when it has never been researched
    (``last_researched_at IS NULL``) or its last research predates ``now`` by
    more than its ``stale_after_days`` window.
    """
    return await repo.list_stale_topics(now.isoformat())


async def refresh_topics(
    orchestrator: ResearchRunner, repo: Repository, *, now: datetime, run: bool
) -> list[Topic]:
    """Return the currently stale topics; when ``run``, re-research and stamp each one.

    Always computes and returns :func:`stale_topics`. When ``run`` is set, each
    stale topic is re-researched via ``orchestrator.research`` (mode
    ``"standard"``) and then stamped with ``last_researched_at = now``.
    """
    stale = await stale_topics(repo, now=now)
    if run:
        for topic in stale:
            if topic.id is None:
                raise RuntimeError(f"stale topic {topic.slug!r} has no id")
            await orchestrator.research(topic_id=topic.id, topic_title=topic.title, mode="standard")
            await repo.set_topic_researched(topic.id, now.isoformat())
    return stale

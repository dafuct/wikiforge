"""Topic-level similarity links computed from article chunk embeddings."""

from __future__ import annotations

import math

from wikiforge.models.domain import Topic
from wikiforge.storage.repository import Repository


async def topic_vector(repo: Repository, topic_id: int) -> list[float] | None:
    """Return the mean of a topic's latest article's chunk vectors, or None."""
    latest = await repo.latest_article_for_topic(topic_id)
    if latest is None or latest.id is None:
        return None
    vectors = await repo.article_chunk_vectors(latest.id)
    if not vectors:
        return None
    dim = len(vectors[0])
    return [sum(v[i] for v in vectors) / len(vectors) for i in range(dim)]


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return 0.0 if na == 0 or nb == 0 else dot / (na * nb)


async def refresh_topic_links(repo: Repository, topic_id: int, *, top_n: int = 5) -> None:
    """Recompute this topic's top-N most similar topics and store them as ``topic_links``."""
    this_vec = await topic_vector(repo, topic_id)
    await repo.clear_topic_links(topic_id)
    if this_vec is None:
        return
    scored: list[tuple[int, float]] = []
    for other_id in await repo.topic_ids_with_articles():
        if other_id == topic_id:
            continue
        other_vec = await topic_vector(repo, other_id)
        if other_vec is None:
            continue
        scored.append((other_id, _cosine(this_vec, other_vec)))
    scored.sort(key=lambda pair: pair[1], reverse=True)
    for other_id, score in scored[:top_n]:
        await repo.upsert_topic_link(topic_id, other_id, score)


async def related_topics(repo: Repository, topic_id: int) -> list[tuple[Topic, float]]:
    """Return the stored related topics (with scores) for a topic, most similar first."""
    out: list[tuple[Topic, float]] = []
    for related_id, score in await repo.topic_links(topic_id):
        topic = await repo.get_topic_by_id(related_id)
        if topic is not None:
            out.append((topic, score))
    return out

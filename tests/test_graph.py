"""Knowledge graph: topic vectors, similarity links, and related lookup."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.graph.links import refresh_topic_links, related_topics
from wikiforge.models.domain import Article, Topic
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def _topic_with_article_vector(repo: Repository, slug: str, vec: list[float]) -> int:
    tid = await repo.upsert_topic(Topic(slug=slug, title=slug.title(), stale_after_days=90))
    aid = await repo.insert_article(
        Article(
            topic_id=tid,
            slug=slug,
            title=slug,
            body_md="b",
            path=f"topics/{slug}/wiki/{slug}.md",
            confidence=0.5,
            compile_digest="d",
            version=1,
        )
    )
    rowid = await repo.insert_chunk("article", aid, 0, "chunk", f"h-{slug}")
    await repo.insert_chunk_vector(rowid, vec)
    return tid


@pytest.fixture
async def repo(wiki_home: Path):
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    yield Repository(db)
    await db.close()


async def test_related_finds_nearest_topic(repo: Repository) -> None:
    a = await _topic_with_article_vector(repo, "alpha", [1.0, 0.0, 0.0, 0.0])
    await _topic_with_article_vector(repo, "beta", [0.9, 0.1, 0.0, 0.0])  # near alpha
    await _topic_with_article_vector(repo, "gamma", [0.0, 0.0, 1.0, 0.0])  # far
    await refresh_topic_links(repo, a, top_n=1)
    related = await related_topics(repo, a)
    assert len(related) == 1
    assert related[0][0].slug == "beta"  # nearest neighbour is beta, not gamma

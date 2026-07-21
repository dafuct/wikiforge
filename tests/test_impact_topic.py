"""Blast radius of a topic: what it rests on, and who shares those foundations."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import Article, RawSource, Topic
from wikiforge.models.enums import SourceType
from wikiforge.ops.impact import build_topic_impact
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

pytestmark = pytest.mark.asyncio


async def _source(repo: Repository, *, content_hash: str, text: str) -> int:
    source_id, _ = await repo.ingest_raw_source(
        RawSource(
            content_hash=content_hash, canonical_url=None, source_type=SourceType.TEXT,
            title=content_hash, text=text,
            fetched_at=datetime.fromisoformat("2026-07-01T00:00:00+00:00"),
        )
    )
    return source_id


async def _article(repo: Repository, *, slug: str) -> tuple[Topic, Article]:
    """upsert_topic returns only the id (int); fetch the full Topic separately —
    build_topic_impact needs the real object, not just its id."""
    topic_id = await repo.upsert_topic(Topic(slug=slug, title=slug.upper()))
    topic = await repo.get_topic(slug)
    assert topic is not None
    article = await repo.insert_next_article_version(
        Article(topic_id=topic_id, slug=slug, title=slug.upper(), body_md="b",
                path="p", confidence=0.9, compile_digest="d", version=0)
    )
    return topic, article


async def test_sources_are_ranked_by_claim_count_with_drift_counted(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        topic, article = await _article(repo, slug="t")
        assert article.id is not None
        heavy = await _source(repo, content_hash="heavy", text="alpha beta")
        light = await _source(repo, content_hash="light", text="gamma")
        await repo.insert_citation(article.id, "c1", heavy, "alpha")
        await repo.insert_citation(article.id, "c2", heavy, "nowhere")
        await repo.insert_citation(article.id, "c3", light, "gamma")

        report = await build_topic_impact(repo, topic, limit=10)

        assert [(r.source.id, r.claim_count, r.drifted_count) for r in report.sources] == [
            (heavy, 2, 1), (light, 1, 0),
        ]
    finally:
        await db.close()


async def test_shared_foundations_name_the_other_topics(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        topic_a, article_a = await _article(repo, slug="a")
        _, article_b = await _article(repo, slug="b")
        assert article_a.id is not None and article_b.id is not None
        shared = await _source(repo, content_hash="shared", text="text")
        await repo.insert_citation(article_a.id, "c1", shared, None)
        await repo.insert_citation(article_b.id, "c2", shared, None)

        report = await build_topic_impact(repo, topic_a, limit=10)

        assert report.shared == {shared: ["b"]}
    finally:
        await db.close()

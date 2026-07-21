"""Audit chains into impact: a drifted source shows what else rests on it."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import Article, RawSource, Topic
from wikiforge.models.enums import SourceType
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

pytestmark = pytest.mark.asyncio


async def _seed_drifted(home: Path) -> None:
    """One source, two topics, two drifted claims against the same source."""
    from wikiforge.config.settings import load_config
    from wikiforge.services import effective_embedding_dim

    db = await Database.open(home, dim=effective_embedding_dim(load_config(home)))
    try:
        repo = Repository(db)
        source_id, _ = await repo.ingest_raw_source(
            RawSource(
                content_hash="h", canonical_url=None, source_type=SourceType.TEXT,
                title="S", text="the real text",
                fetched_at=datetime.fromisoformat("2026-07-01T00:00:00+00:00"),
            )
        )
        for slug in ("a", "b"):
            # upsert_topic returns the topic's id directly (int), not a Topic object.
            topic_id = await repo.upsert_topic(Topic(slug=slug, title=slug.upper()))
            article = await repo.insert_next_article_version(
                Article(topic_id=topic_id, slug=slug, title=slug.upper(), body_md="b",
                        path="p", confidence=0.9, compile_digest="d", version=0)
            )
            assert article.id is not None
            await repo.insert_citation(article.id, f"claim {slug}", source_id, "never written")
    finally:
        await db.close()


async def test_audit_reports_the_blast_radius_of_each_drifted_source(wiki_home: Path) -> None:
    from wikiforge import services

    await services.init_wiki("T", wiki_home)
    await _seed_drifted(wiki_home)

    result = await services.run_audit(wiki_home, "a")

    assert len(result.findings) == 1
    assert len(result.impacts) == 1
    assert sorted(result.impacts[0].topics) == ["a", "b"]


async def test_one_impact_per_distinct_source_not_per_finding(wiki_home: Path) -> None:
    """Two drifted claims on one source must not produce two identical reports."""
    from wikiforge import services
    from wikiforge.config.settings import load_config

    await services.init_wiki("T", wiki_home)
    await _seed_drifted(wiki_home)
    dim = services.effective_embedding_dim(load_config(wiki_home))
    db = await Database.open(wiki_home, dim=dim)
    try:
        repo = Repository(db)
        topic = await repo.get_topic("a")
        assert topic is not None and topic.id is not None
        article = await repo.latest_article_for_topic(topic.id)
        assert article is not None and article.id is not None
        source = await repo.get_raw_source_by_hash("h")
        assert source is not None and source.id is not None
        await repo.insert_citation(article.id, "second claim", source.id, "also missing")
    finally:
        await db.close()

    result = await services.run_audit(wiki_home, "a")

    assert len(result.findings) == 2
    assert len(result.impacts) == 1


async def test_no_impact_flag_skips_the_chain(wiki_home: Path) -> None:
    from wikiforge import services

    await services.init_wiki("T", wiki_home)
    await _seed_drifted(wiki_home)

    result = await services.run_audit(wiki_home, "a", impact=False)

    assert result.findings and result.impacts == []

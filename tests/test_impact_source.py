"""Blast radius of a source: which claims, in which live articles, rest on it."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import Article, RawSource, Topic
from wikiforge.models.enums import SourceType
from wikiforge.ops.impact import build_source_impact
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

pytestmark = pytest.mark.asyncio


async def _source(repo: Repository, *, text: str) -> RawSource:
    source_id, _ = await repo.ingest_raw_source(
        RawSource(
            content_hash="h", canonical_url=None, source_type=SourceType.TEXT,
            title="S", text=text,
            fetched_at=datetime.fromisoformat("2026-07-01T00:00:00+00:00"),
        )
    )
    found = await repo.get_raw_source_by_id(source_id)
    assert found is not None
    return found


async def _article(repo: Repository, *, slug: str, title: str) -> Article:
    """upsert_topic returns the topic's id directly (int), not a Topic object."""
    topic_id = await repo.upsert_topic(Topic(slug=slug, title=title))
    return await repo.insert_next_article_version(
        Article(topic_id=topic_id, slug=slug, title=title, body_md="b",
                path="p", confidence=0.9, compile_digest="d", version=0)
    )


async def test_current_claims_come_first_and_define_the_topic_list(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        source = await _source(repo, text="the exact source text")
        old = await _article(repo, slug="t", title="T")
        new = await _article(repo, slug="t", title="T")
        assert old.id is not None and new.id is not None
        await repo.insert_citation(old.id, "stale claim", source.id or 0, "the exact")
        await repo.insert_citation(new.id, "live claim", source.id or 0, "the exact")

        report = await build_source_impact(repo, source, limit=10)

        assert [c.claim for c in report.claims] == ["live claim", "stale claim"]
        assert [c.is_current for c in report.claims] == [True, False]
        assert report.topics == ["t"]
    finally:
        await db.close()


async def test_drifted_quotes_are_flagged(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        source = await _source(repo, text="the exact source text")
        article = await _article(repo, slug="t", title="T")
        assert article.id is not None
        await repo.insert_citation(article.id, "ok", source.id or 0, "exact source")
        await repo.insert_citation(article.id, "bad", source.id or 0, "never written")

        report = await build_source_impact(repo, source, limit=10)

        assert {c.claim: c.drifted for c in report.claims} == {"ok": False, "bad": True}
    finally:
        await db.close()


async def test_an_uncited_source_reports_an_empty_radius(wiki_home: Path) -> None:
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    try:
        source = await _source(repo, text="nobody cites me")

        report = await build_source_impact(repo, source, limit=10)

        assert report.claims == [] and report.topics == [] and report.findings == []
    finally:
        await db.close()

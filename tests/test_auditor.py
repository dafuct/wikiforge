"""WikiAuditor: re-verifies citation quotes against their immutable raw sources."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.lint.auditor import WikiAuditor
from wikiforge.models.domain import Article, RawSource, Topic
from wikiforge.models.enums import SourceType, Volatility
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def repo(wiki_home: Path):
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    yield Repository(db)
    await db.close()


async def _make_topic(repo: Repository, slug: str, title: str) -> Topic:
    """Create and return a persisted (id-populated) topic."""
    await repo.upsert_topic(
        Topic(slug=slug, title=title, volatility=Volatility.LOW, stale_after_days=90)
    )
    topic = await repo.get_topic(slug)
    assert topic is not None
    return topic


async def _make_article(repo: Repository, topic: Topic, *, version: int = 1) -> Article:
    """Insert and return a (id-populated) compiled article for ``topic``."""
    assert topic.id is not None
    article = Article(
        topic_id=topic.id,
        slug=topic.slug,
        title=topic.title,
        body_md="body",
        path=f"topics/{topic.slug}/wiki/{topic.slug}.md",
        confidence=0.5,
        compile_digest="d",
        version=version,
    )
    article_id = await repo.insert_article(article)
    return article.model_copy(update={"id": article_id})


async def _make_raw_source(repo: Repository, text: str, content_hash: str) -> int:
    """Ingest and return the id of a raw source with the given text."""
    source = RawSource(
        content_hash=content_hash,
        source_type=SourceType.URL,
        canonical_url="https://example.com",
        title="Source",
        text=text,
        fetched_at=datetime.now(UTC),
    )
    source_id, _created = await repo.ingest_raw_source(source)
    return source_id


async def test_audit_flags_only_the_drifted_citation(repo: Repository) -> None:
    topic = await _make_topic(repo, "fox", "The Fox")
    article = await _make_article(repo, topic)
    assert article.id is not None
    source_id = await _make_raw_source(repo, "the quick brown fox jumps", "hash-1")

    await repo.insert_citation(article.id, "claim present", source_id, "quick brown")
    await repo.insert_citation(article.id, "claim absent", source_id, "lazy dog")
    await repo.insert_citation(article.id, "claim no quote", source_id, None)

    findings = await WikiAuditor(repo).audit_topic("fox")

    assert len(findings) == 1
    finding = findings[0]
    assert finding.article_slug == "fox"
    assert finding.claim == "claim absent"
    assert finding.raw_source_id == source_id
    assert "not found" in finding.issue


async def test_clean_topic_yields_no_findings(repo: Repository) -> None:
    topic = await _make_topic(repo, "clean", "Clean Topic")
    article = await _make_article(repo, topic)
    assert article.id is not None
    source_id = await _make_raw_source(repo, "everything checks out fine", "hash-clean")

    await repo.insert_citation(article.id, "claim ok", source_id, "checks out")

    findings = await WikiAuditor(repo).audit_topic("clean")

    assert findings == []


async def test_normalized_match_is_whitespace_and_case_insensitive(repo: Repository) -> None:
    topic = await _make_topic(repo, "fox2", "The Fox 2")
    article = await _make_article(repo, topic)
    assert article.id is not None
    source_id = await _make_raw_source(repo, "the  Quick   Brown fox", "hash-2")

    await repo.insert_citation(article.id, "claim", source_id, "quick brown")

    findings = await WikiAuditor(repo).audit_topic("fox2")

    assert findings == []


async def test_unknown_topic_raises_value_error(repo: Repository) -> None:
    with pytest.raises(ValueError):
        await WikiAuditor(repo).audit_topic("nonexistent")

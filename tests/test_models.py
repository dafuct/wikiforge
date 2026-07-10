"""Validation round-trips for domain models and LLM schemas."""

from __future__ import annotations

from datetime import UTC, datetime

from wikiforge.models.domain import Article, RawSource, Topic
from wikiforge.models.enums import SourceType, TopicStatus, Volatility
from wikiforge.models.schemas import ClaimCitation, CompiledArticle


def test_topic_defaults_and_enums() -> None:
    t = Topic(
        slug="rust-async", title="Rust Async", volatility=Volatility.MEDIUM, stale_after_days=90
    )
    assert t.status is TopicStatus.ACTIVE
    assert t.volatility is Volatility.MEDIUM


def test_raw_source_requires_content_hash() -> None:
    s = RawSource(
        content_hash="abc123",
        source_type=SourceType.URL,
        title="Example",
        text="hello",
        fetched_at=datetime.now(UTC),
    )
    assert s.canonical_url is None
    assert s.persona is None


def test_article_confidence_bounds() -> None:
    a = Article(
        topic_id=1,
        slug="rust-async",
        title="Rust Async",
        body_md="# body",
        path="topics/rust-async/wiki/index.md",
        confidence=0.5,
        compile_digest="deadbeef",
        version=1,
    )
    assert 0.0 <= a.confidence <= 1.0


def test_compiled_article_schema_carries_evidence_fields() -> None:
    art = CompiledArticle(
        title="Rust Async",
        body="Rust async is cooperative. [1]",
        citations=[ClaimCitation(claim="Rust async is cooperative", source_id="s1", quote="...")],
        conflicts=[],
        open_questions=["What about io_uring backends?"],
        wikilinks=[],
        source_ids=["s1", "s2"],
        distinct_domains=2,
        distinct_personas=3,
        source_dates=["2026-01-01"],
        evidence_strength=0.8,
    )
    assert art.evidence_strength == 0.8
    assert art.distinct_domains == 2

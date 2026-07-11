"""Repository CRUD, including raw-source dedup by content hash."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import ActivityEntry, LlmCall, RawSource, Topic
from wikiforge.models.enums import SourceType, Volatility
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def repo(wiki_home: Path):
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    yield Repository(db)
    await db.close()


async def test_upsert_and_get_topic(repo: Repository) -> None:
    tid = await repo.upsert_topic(
        Topic(
            slug="rust-async", title="Rust Async", volatility=Volatility.MEDIUM, stale_after_days=90
        )
    )
    assert tid > 0
    got = await repo.get_topic("rust-async")
    assert got is not None
    assert got.title == "Rust Async"


async def test_upsert_topic_is_idempotent_on_slug(repo: Repository) -> None:
    first = await repo.upsert_topic(Topic(slug="x", title="First", stale_after_days=90))
    second = await repo.upsert_topic(Topic(slug="x", title="Second", stale_after_days=90))
    assert first == second
    got = await repo.get_topic("x")
    assert got is not None and got.title == "Second"


async def test_raw_source_dedup_updates_provenance(repo: Repository) -> None:
    src = RawSource(
        content_hash="hash-1",
        source_type=SourceType.URL,
        canonical_url="https://example.com/a",
        title="A",
        text="body",
        fetched_at=datetime.now(UTC),
        provenance={"seen": "first"},
    )
    id1, created1 = await repo.ingest_raw_source(src)
    assert created1 is True

    dup = src.model_copy(update={"provenance": {"seen": "second"}})
    id2, created2 = await repo.ingest_raw_source(dup)
    assert created2 is False
    assert id2 == id1  # same row, not a duplicate

    stored = await repo.get_raw_source_by_hash("hash-1")
    assert stored is not None
    assert stored.provenance == {"seen": "second"}
    assert stored.text == "body"  # immutable text unchanged


async def test_insert_activity_and_llm_call(repo: Repository) -> None:
    aid = await repo.insert_activity(ActivityEntry(command="init", summary="created wiki"))
    assert aid > 0
    lid = await repo.insert_llm_call(
        LlmCall(
            provider="anthropic",
            model="claude-haiku-4-5",
            purpose="extract",
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.00035,
        )
    )
    assert lid > 0

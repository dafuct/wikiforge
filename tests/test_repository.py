"""Repository CRUD, including raw-source dedup by content hash."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.models.domain import ActivityEntry, Article, LlmCall, RawSource, Topic
from wikiforge.models.enums import SourceType, Volatility
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def repo(wiki_home: Path):
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    yield Repository(db)
    await db.close()


@pytest.fixture
async def db_repo(wiki_home):
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    yield db, Repository(db)
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


async def _dev_event(repo, text: str, *, pending: bool) -> int:
    src = RawSource(
        content_hash=f"h-{text[:16]}", source_type=SourceType.DEV_EVENT,
        title="Dev event", text=text, fetched_at=datetime(2026, 7, 15, tzinfo=UTC),
        provenance={"digest": "pending"} if pending else {},
    )
    source_id, _ = await repo.ingest_raw_source(src)
    return source_id


async def test_chunk_targets_populates_owner_ts_and_source_type(db_repo) -> None:
    db, repo = db_repo
    src = RawSource(
        content_hash="h-recency", source_type=SourceType.DEV_EVENT,
        title="Dev event", text="dev event chunk text",
        fetched_at=datetime(2026, 7, 15, tzinfo=UTC),
        provenance={"ts": "2026-07-01T00:00:00Z", "type": "bugfix"},
    )
    sid, _ = await repo.ingest_raw_source(src)
    rowid = await repo.insert_chunk(
        owner_type="raw_source", owner_id=sid, seq=0, text="dev event chunk text",
        content_hash="c-dev",
    )

    topic_id = await repo.upsert_topic(
        Topic(slug="art-topic", title="Art Topic", stale_after_days=90)
    )
    article = Article(
        topic_id=topic_id, slug="art-topic", title="Art Topic", body_md="article body",
        path="art-topic.md", confidence=0.61, compile_digest="d1", version=1,
    )
    article_id = await repo.insert_article(article)
    art_rowid = await repo.insert_chunk(
        owner_type="article", owner_id=article_id, seq=0, text="article body",
        content_hash="c-art",
    )

    [dev_target] = await repo.chunk_targets([rowid])
    assert dev_target.owner_ts == "2026-07-01T00:00:00Z"
    assert dev_target.owner_source_type == "dev_event"
    assert dev_target.owner_event_type == "bugfix"

    [art_target] = await repo.chunk_targets([art_rowid])
    assert art_target.owner_ts is None
    assert art_target.article_confidence == 0.61
    assert art_target.topic_volatility == "MEDIUM"
    assert art_target.topic_last_researched_at is None


async def test_chunks_missing_vectors_lists_unembedded(db_repo) -> None:
    db, repo = db_repo
    sid = await _dev_event(repo, "alpha beta gamma", pending=False)
    rowid = await repo.insert_chunk(
        owner_type="raw_source", owner_id=sid, seq=0, text="alpha beta gamma", content_hash="c1"
    )
    missing = await repo.chunks_missing_vectors(owner_type="raw_source", limit=10)
    assert (rowid, "alpha beta gamma") in missing
    await repo.insert_chunk_vector(rowid, [0.0, 0.0, 0.0, 1.0])
    assert await repo.chunks_missing_vectors(owner_type="raw_source", limit=10) == []


async def test_dev_events_pending_digest_filters_on_provenance(db_repo) -> None:
    db, repo = db_repo
    await _dev_event(repo, "pending one", pending=True)
    await _dev_event(repo, "done one", pending=False)
    events = await repo.dev_events_pending_digest(limit=10)
    assert [e.text for e in events] == ["pending one"]


async def test_count_dev_events_pending_digest_exceeds_batch_limit(db_repo) -> None:
    db, repo = db_repo
    await _dev_event(repo, "pending one", pending=True)
    await _dev_event(repo, "pending two", pending=True)
    await _dev_event(repo, "pending three", pending=True)
    await _dev_event(repo, "done one", pending=False)
    # A small batch limit must not cap the reported count.
    assert await repo.dev_events_pending_digest(limit=2)
    assert await repo.count_dev_events_pending_digest() == 3


async def test_set_raw_source_provenance_updates_only_provenance(db_repo) -> None:
    db, repo = db_repo
    await _dev_event(repo, "pending two", pending=True)
    src = (await repo.dev_events_pending_digest(limit=10))[0]
    await repo.set_raw_source_provenance(src.content_hash, {"digest": "done", "summary": "S"})
    again = await repo.get_raw_source_by_hash(src.content_hash)
    assert again is not None
    assert again.provenance == {"digest": "done", "summary": "S"}
    assert again.text == "pending two"  # text untouched
    assert await repo.dev_events_pending_digest(limit=10) == []


async def test_fts_search_raw_source_scope(db_repo) -> None:
    db, repo = db_repo
    sid = await _dev_event(repo, "zebra quartz devlog entry", pending=False)
    await repo.insert_chunk(
        owner_type="raw_source", owner_id=sid, seq=0,
        text="zebra quartz devlog entry", content_hash="c2",
    )
    hits_raw = await repo.fts_search('"zebra"', ["raw_source"], 10)
    hits_articles = await repo.fts_search('"zebra"', ["article"], 10)
    assert hits_raw and not hits_articles


async def _dev_event_with_files(
    repo: Repository, *, title: str, files: list[str], fetched_at: str
) -> int:
    """Insert one DEV_EVENT raw source plus its file-index rows; return its id."""
    source_id, _ = await repo.ingest_raw_source(
        RawSource(
            content_hash=title,
            canonical_url=None,
            source_type=SourceType.DEV_EVENT,
            title=title,
            text=title,
            fetched_at=datetime.fromisoformat(fetched_at),
            provenance={"files": ",".join(files), "type": "change"},
        )
    )
    if files:
        await repo.add_dev_event_files(source_id, files)
    return source_id


async def test_dev_events_for_paths_matches_any_of_the_given_paths(db_repo) -> None:
    db, repo = db_repo
    await repo.ensure_dev_event_files()
    a = await _dev_event_with_files(
        repo, title="a", files=["/r/x.py"], fetched_at="2026-07-01T00:00:00+00:00"
    )
    b = await _dev_event_with_files(
        repo, title="b", files=["/r/y.py"], fetched_at="2026-07-02T00:00:00+00:00"
    )
    await _dev_event_with_files(
        repo, title="c", files=["/r/z.py"], fetched_at="2026-07-03T00:00:00+00:00"
    )

    found = await repo.dev_events_for_paths(["/r/x.py", "/r/y.py"], limit=10)

    assert {e.id for e in found} == {a, b}


async def test_dev_events_for_paths_yields_one_row_per_event(db_repo) -> None:
    """An event touching several queried paths must not be returned twice."""
    db, repo = db_repo
    await repo.ensure_dev_event_files()
    only = await _dev_event_with_files(
        repo, title="multi", files=["/r/x.py", "/r/y.py"],
        fetched_at="2026-07-01T00:00:00+00:00",
    )

    found = await repo.dev_events_for_paths(["/r/x.py", "/r/y.py"], limit=10)

    assert [e.id for e in found] == [only]


async def test_dev_events_for_paths_survives_more_than_999_paths(db_repo) -> None:
    """The JSON-array expansion exists so a big branch can't hit SQLite's parameter cap."""
    db, repo = db_repo
    await repo.ensure_dev_event_files()
    wanted = await _dev_event_with_files(
        repo, title="hit", files=["/r/needle.py"], fetched_at="2026-07-01T00:00:00+00:00"
    )
    paths = [f"/r/miss{i}.py" for i in range(1500)] + ["/r/needle.py"]

    found = await repo.dev_events_for_paths(paths, limit=10)

    assert [e.id for e in found] == [wanted]


async def test_dev_events_for_paths_limit_counts_events_not_rows(db_repo) -> None:
    db, repo = db_repo
    await repo.ensure_dev_event_files()
    await _dev_event_with_files(
        repo, title="a", files=["/r/x.py", "/r/y.py"], fetched_at="2026-07-01T00:00:00+00:00"
    )
    await _dev_event_with_files(
        repo, title="b", files=["/r/x.py", "/r/y.py"], fetched_at="2026-07-02T00:00:00+00:00"
    )

    found = await repo.dev_events_for_paths(["/r/x.py", "/r/y.py"], limit=2)

    assert len(found) == 2


async def test_matched_dev_event_paths_is_exact_and_limit_free(db_repo) -> None:
    """Coverage is computed independently of the event limit, so it can't under-report."""
    db, repo = db_repo
    await repo.ensure_dev_event_files()
    await _dev_event_with_files(
        repo, title="a", files=["/r/x.py"], fetched_at="2026-07-01T00:00:00+00:00"
    )
    await _dev_event_with_files(
        repo, title="b", files=["/r/y.py"], fetched_at="2026-07-02T00:00:00+00:00"
    )

    matched = await repo.matched_dev_event_paths(["/r/x.py", "/r/y.py", "/r/never.py"])

    assert matched == {"/r/x.py", "/r/y.py"}


async def test_dev_events_fileless_in_window_selects_only_events_with_no_files(
    db_repo,
) -> None:
    db, repo = db_repo
    await repo.ensure_dev_event_files()
    bare = await _dev_event_with_files(
        repo, title="bare", files=[], fetched_at="2026-07-02T12:00:00+00:00"
    )
    await _dev_event_with_files(
        repo, title="withfile", files=["/r/x.py"], fetched_at="2026-07-02T13:00:00+00:00"
    )
    await _dev_event_with_files(
        repo, title="early", files=[], fetched_at="2026-06-01T00:00:00+00:00"
    )

    found = await repo.dev_events_fileless_in_window(
        "2026-07-02T00:00:00.000000+00:00", "2026-07-02T23:59:59.999999+00:00", limit=10
    )

    assert [e.id for e in found] == [bare]


async def test_co_changed_paths_ranks_by_shared_events(db_repo) -> None:
    db, repo = db_repo
    await repo.ensure_dev_event_files()
    await _dev_event_with_files(
        repo, title="1", files=["/r/x.py", "/r/near.py"], fetched_at="2026-07-01T00:00:00+00:00"
    )
    await _dev_event_with_files(
        repo, title="2", files=["/r/x.py", "/r/near.py"], fetched_at="2026-07-02T00:00:00+00:00"
    )
    await _dev_event_with_files(
        repo, title="3", files=["/r/x.py", "/r/far.py"], fetched_at="2026-07-03T00:00:00+00:00"
    )

    co = await repo.co_changed_paths("/r/x.py", limit=10)

    assert co == [("/r/near.py", 2), ("/r/far.py", 1)]


async def test_co_changed_paths_accepts_a_relative_suffix(db_repo) -> None:
    """A caller outside a git repo has no absolute form to anchor with."""
    db, repo = db_repo
    await repo.ensure_dev_event_files()
    await _dev_event_with_files(
        repo, title="1", files=["/r/x.py", "/r/near.py"], fetched_at="2026-07-01T00:00:00+00:00"
    )

    co = await repo.co_changed_paths("x.py", limit=10)

    assert co == [("/r/near.py", 1)]

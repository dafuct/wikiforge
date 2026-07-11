"""Knowledge-ops tests: feedback store, freshness/refresh (Milestone 4 Task 6).

Task 7 appends inventory/dataset/archive test sections to this same file —
each concern gets its own ``# --- Name ---`` banner and shares the ``repo``
fixture below, so new sections can be added without touching existing ones.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from wikiforge.models.domain import Article, Topic
from wikiforge.models.enums import FeedbackVerdict, TopicStatus
from wikiforge.ops.feedback import FeedbackStore
from wikiforge.ops.freshness import refresh_topics, stale_topics
from wikiforge.ops.inventory import add_dataset, archive_topic, collect
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def repo(wiki_home: Path):
    """An open repository backed by a fresh, schema-initialized wiki DB."""
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    yield Repository(db)
    await db.close()


# --- Feedback ----------------------------------------------------------------


async def test_record_feedback_returns_positive_id(repo: Repository) -> None:
    store = FeedbackStore(repo)
    feedback_id = await store.record("article", 1, FeedbackVerdict.CORRECT, "fix X")
    assert feedback_id > 0


async def test_for_topic_returns_feedback_linked_via_article(repo: Repository) -> None:
    topic_id = await repo.upsert_topic(Topic(slug="t", title="T", stale_after_days=90))
    article_id = await repo.insert_article(
        Article(
            topic_id=topic_id,
            slug="t",
            title="T",
            body_md="body",
            path="topics/t/wiki/t.md",
            confidence=0.5,
            compile_digest="d",
            version=1,
        )
    )
    store = FeedbackStore(repo)
    feedback_id = await store.record("article", article_id, FeedbackVerdict.CORRECT, "fix X")

    results = await store.for_topic(topic_id)

    assert len(results) == 1
    assert results[0].id == feedback_id
    assert results[0].target_type == "article"
    assert results[0].target_id == article_id
    assert results[0].verdict is FeedbackVerdict.CORRECT
    assert results[0].note == "fix X"


async def test_for_topic_excludes_feedback_on_other_articles(repo: Repository) -> None:
    topic_a = await repo.upsert_topic(Topic(slug="a", title="A", stale_after_days=90))
    topic_b = await repo.upsert_topic(Topic(slug="b", title="B", stale_after_days=90))
    article_b = await repo.insert_article(
        Article(
            topic_id=topic_b,
            slug="b",
            title="B",
            body_md="body",
            path="topics/b/wiki/b.md",
            confidence=0.5,
            compile_digest="d",
            version=1,
        )
    )
    store = FeedbackStore(repo)
    await store.record("article", article_b, FeedbackVerdict.REJECT, "wrong topic")

    assert await store.for_topic(topic_a) == []


# --- Freshness -----------------------------------------------------------------


async def test_never_researched_topic_is_stale(repo: Repository) -> None:
    await repo.upsert_topic(Topic(slug="never", title="Never", stale_after_days=90))
    now = datetime(2026, 7, 11, tzinfo=UTC)

    stale = await stale_topics(repo, now=now)

    assert [t.slug for t in stale] == ["never"]


async def test_recently_researched_topic_is_not_stale(repo: Repository) -> None:
    tid = await repo.upsert_topic(Topic(slug="fresh", title="Fresh", stale_after_days=365))
    now = datetime(2026, 7, 11, tzinfo=UTC)
    await repo.set_topic_researched(tid, now.isoformat())

    stale = await stale_topics(repo, now=now)

    assert stale == []


async def test_long_ago_researched_topic_is_stale(repo: Repository) -> None:
    tid = await repo.upsert_topic(Topic(slug="old", title="Old", stale_after_days=30))
    researched_at = datetime(2026, 1, 1, tzinfo=UTC)
    await repo.set_topic_researched(tid, researched_at.isoformat())
    now = datetime(2026, 7, 11, tzinfo=UTC)

    stale = await stale_topics(repo, now=now)

    assert [t.slug for t in stale] == ["old"]


async def test_archived_topic_is_never_stale(repo: Repository) -> None:
    from wikiforge.models.enums import TopicStatus

    await repo.upsert_topic(
        Topic(slug="gone", title="Gone", status=TopicStatus.ARCHIVED, stale_after_days=1)
    )
    now = datetime(2026, 7, 11, tzinfo=UTC)

    assert await stale_topics(repo, now=now) == []


class _FakeOrchestrator:
    """Records ``research`` calls instead of hitting the network."""

    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    async def research(self, *, topic_id: int, topic_title: str, mode: str) -> None:
        self.calls.append({"topic_id": topic_id, "topic_title": topic_title, "mode": mode})


async def test_refresh_topics_without_run_only_lists(repo: Repository) -> None:
    await repo.upsert_topic(Topic(slug="never", title="Never", stale_after_days=90))
    now = datetime(2026, 7, 11, tzinfo=UTC)
    orch = _FakeOrchestrator()

    stale = await refresh_topics(orch, repo, now=now, run=False)

    assert [t.slug for t in stale] == ["never"]
    assert orch.calls == []
    topic = await repo.get_topic("never")
    assert topic is not None and topic.last_researched_at is None


async def test_refresh_topics_run_researches_and_stamps_each_stale_topic(
    repo: Repository,
) -> None:
    t1 = await repo.upsert_topic(Topic(slug="a", title="A", stale_after_days=90))
    t2 = await repo.upsert_topic(Topic(slug="b", title="B", stale_after_days=90))
    now = datetime(2026, 7, 11, tzinfo=UTC)
    orch = _FakeOrchestrator()

    stale = await refresh_topics(orch, repo, now=now, run=True)

    assert {t.slug for t in stale} == {"a", "b"}
    assert {c["topic_id"] for c in orch.calls} == {t1, t2}
    assert all(c["mode"] == "standard" for c in orch.calls)

    topic_a = await repo.get_topic("a")
    topic_b = await repo.get_topic("b")
    assert topic_a is not None and topic_a.last_researched_at is not None
    assert topic_b is not None and topic_b.last_researched_at is not None


# --- Services / CLI wiring -----------------------------------------------------


async def test_run_feedback_parses_prefixed_target(wiki_home: Path) -> None:
    from wikiforge.services import init_wiki, run_feedback

    await init_wiki("w", wiki_home)
    feedback_id = await run_feedback(wiki_home, "article:7", "approve", "looks right")
    assert feedback_id > 0


async def test_run_feedback_defaults_to_article_for_bare_id(wiki_home: Path) -> None:
    from wikiforge.services import init_wiki, run_feedback

    await init_wiki("w", wiki_home)
    feedback_id = await run_feedback(wiki_home, "7", "reject", "wrong")
    assert feedback_id > 0


async def test_run_feedback_supports_finding_target(wiki_home: Path) -> None:
    from wikiforge.services import init_wiki, run_feedback

    await init_wiki("w", wiki_home)
    feedback_id = await run_feedback(wiki_home, "finding:2", "correct", "needs a fix")
    assert feedback_id > 0


async def test_run_refresh_without_run_lists_only(wiki_home: Path) -> None:
    from wikiforge.config.settings import load_config
    from wikiforge.embed.factory import effective_embedding_dim
    from wikiforge.services import init_wiki, run_refresh

    await init_wiki("w", wiki_home)
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=effective_embedding_dim(cfg))
    await Repository(db).upsert_topic(Topic(slug="never", title="Never", stale_after_days=90))
    await db.close()

    stale = await run_refresh(wiki_home, run=False)

    assert [t.slug for t in stale] == ["never"]


def test_cli_feedback_command(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from wikiforge.cli.app import app

    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    result = CliRunner().invoke(
        app, ["feedback", "3", "approve", "looks good", "--home", str(home)]
    )
    assert result.exit_code == 0


def test_cli_refresh_without_run_lists_stale_topics(tmp_path: Path) -> None:
    from typer.testing import CliRunner

    from wikiforge.cli.app import app

    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])
    result = CliRunner().invoke(app, ["refresh", "--home", str(home)])
    assert result.exit_code == 0


def test_wiki_refresh_lists_stale_topics(tmp_path: Path) -> None:
    import asyncio

    from typer.testing import CliRunner

    from wikiforge.cli.app import app
    from wikiforge.config.settings import load_config
    from wikiforge.embed.factory import effective_embedding_dim

    home = tmp_path / "w"
    CliRunner().invoke(app, ["init", "demo", "--home", str(home)])

    async def _seed() -> None:
        cfg = load_config(home)
        db = await Database.open(home, dim=effective_embedding_dim(cfg))
        try:
            await Repository(db).upsert_topic(
                Topic(slug="fresh-me", title="Fresh Me", stale_after_days=90)
            )
        finally:
            await db.close()

    asyncio.run(_seed())
    result = CliRunner().invoke(app, ["refresh", "--home", str(home)])
    assert result.exit_code == 0
    assert "fresh-me" in result.stdout  # never-researched topic listed as stale
    assert "stale" in result.stdout.lower()


# --- Datasets (Task 7) ---------------------------------------------------------


async def test_add_dataset_records_name_path_and_bytes(repo: Repository, tmp_path: Path) -> None:
    data_file = tmp_path / "data.csv"
    data_file.write_bytes(b"a,b,c\n1,2,3\n")

    dataset = await add_dataset(repo, "my-data", data_file)

    assert dataset.id is not None and dataset.id > 0
    assert dataset.name == "my-data"
    assert dataset.path == str(data_file)
    assert dataset.bytes == data_file.stat().st_size == len(b"a,b,c\n1,2,3\n")


# --- Archive (Task 7) ------------------------------------------------------------


async def test_archive_topic_sets_status_archived(repo: Repository) -> None:
    await repo.upsert_topic(
        Topic(slug="old-topic", title="Old Topic", status=TopicStatus.ACTIVE, stale_after_days=90)
    )

    archived = await archive_topic(repo, "old-topic")

    assert archived.status is TopicStatus.ARCHIVED
    reloaded = await repo.get_topic("old-topic")
    assert reloaded is not None
    assert reloaded.status is TopicStatus.ARCHIVED


async def test_archive_unknown_topic_raises(repo: Repository) -> None:
    with pytest.raises(ValueError, match="unknown"):
        await archive_topic(repo, "does-not-exist")


# --- Collect / inventory (Task 7) -------------------------------------------------


async def test_collect_file_target_records_inventory_item_linked_to_raw_source(
    repo: Repository, wiki_home: Path
) -> None:
    doc = wiki_home / "tool-notes.txt"
    doc.write_text("A note about a handy CLI tool.", encoding="utf-8")

    async with httpx.AsyncClient() as client:
        item = await collect(repo, wiki_home, "tools", str(doc), http_client=client)

    assert item.id is not None and item.id > 0
    assert item.collection_name == "tools"
    assert item.kind == "file"
    assert item.name == doc.name
    assert item.source_id is not None

    listed = await repo.list_inventory("tools")
    assert [i.id for i in listed] == [item.id]
    assert listed[0].source_id == item.source_id


# --- Archive + retrieval integration (Task 7, confirms Task 2 coverage) --------------


async def test_archived_topic_excluded_from_retrieval(wiki_home: Path) -> None:
    """Short confirmation that archiving flows into retrieval exclusion (full coverage: Task 2)."""
    from wikiforge.config.settings import load_config, write_default_config
    from wikiforge.search.index import index_owner
    from wikiforge.search.retriever import HybridRetriever

    class _KeywordEmbedder:
        @property
        def dim(self) -> int:
            return 4

        @property
        def model(self) -> str:
            return "kw"

        @property
        def provider_name(self) -> str:
            return "kw"

        async def embed(self, texts: list[str]) -> list[list[float]]:
            return [[1.0 if "gizmo" in t.lower() else 0.0, 0.1, 0.1, 0.1] for t in texts]

    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    embedder = _KeywordEmbedder()

    topic_id = await repo.upsert_topic(
        Topic(slug="archived-integration", title="Archived Integration", stale_after_days=90)
    )
    article_id = await repo.insert_article(
        Article(
            topic_id=topic_id,
            slug="archived-integration",
            title="Archived Integration",
            body_md="# Archived Integration\n\nThe gizmo widget does a thing.",
            path="topics/archived-integration/wiki/archived-integration.md",
            confidence=0.9,
            compile_digest="d",
            version=1,
        )
    )
    await index_owner(
        repo,
        embedder,
        owner_type="article",
        owner_id=article_id,
        text="# Archived Integration\n\nThe gizmo widget does a thing.",
    )

    await archive_topic(repo, "archived-integration")

    retriever = HybridRetriever(repo, embedder, cfg)
    hits = await retriever.retrieve("gizmo widget", depth="quick")
    assert all("gizmo" not in h.text.lower() for h in hits)

    await db.close()

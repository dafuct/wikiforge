"""WikiLinter: broken wikilinks, orphans, missing citations, stale confidence, and fix()."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.lint.linter import WikiLinter
from wikiforge.models.domain import Article, RawSource, ResearchFinding, ResearchSession, Topic
from wikiforge.models.enums import SourceType, Volatility
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def env(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    (wiki_home / "topics").mkdir(exist_ok=True)
    load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    yield repo, wiki_home
    await db.close()


async def _make_topic(repo: Repository, slug: str, title: str) -> Topic:
    """Create and return a persisted (id-populated) ACTIVE topic."""
    await repo.upsert_topic(
        Topic(slug=slug, title=title, volatility=Volatility.LOW, stale_after_days=90)
    )
    topic = await repo.get_topic(slug)
    assert topic is not None
    return topic


async def _compile_article(
    repo: Repository, home: Path, topic: Topic, body_md: str, *, version: int = 1
) -> Article:
    """Insert an article row for ``topic`` and write matching Markdown to disk."""
    assert topic.id is not None
    wiki_dir = home / "topics" / topic.slug / "wiki"
    wiki_dir.mkdir(parents=True, exist_ok=True)
    path = wiki_dir / f"{topic.slug}.md"
    path.write_text(body_md, encoding="utf-8")
    article = Article(
        topic_id=topic.id,
        slug=topic.slug,
        title=topic.title,
        body_md=body_md,
        path=str(path.relative_to(home)),
        confidence=0.5,
        compile_digest="d",
        version=version,
    )
    article_id = await repo.insert_article(article)
    return article.model_copy(update={"id": article_id})


async def test_broken_wikilink_finding(env) -> None:
    repo, home = env
    topic = await _make_topic(repo, "real", "Real Topic")
    await _compile_article(repo, home, topic, "See [[ghost|Ghost Topic]] for more.")

    findings = await WikiLinter(repo).lint()

    broken = [f for f in findings if f.kind == "broken_wikilink"]
    assert len(broken) == 1
    assert broken[0].topic_slug == "real"
    assert broken[0].detail == "[[ghost|Ghost Topic]] -> no such topic"


async def test_valid_wikilink_is_not_flagged(env) -> None:
    repo, home = env
    a = await _make_topic(repo, "a", "Topic A")
    b = await _make_topic(repo, "b", "Topic B")
    await _compile_article(repo, home, a, "See [[b|Topic B]] for more.")
    await _compile_article(repo, home, b, "Nothing here.")

    findings = await WikiLinter(repo).lint()

    assert [f for f in findings if f.kind == "broken_wikilink"] == []


async def test_missing_citation_finding(env) -> None:
    repo, home = env
    topic = await _make_topic(repo, "cited", "Cited Topic")
    assert topic.id is not None
    src = RawSource(
        content_hash="s1",
        source_type=SourceType.TEXT,
        title="src",
        text="source text",
        fetched_at=datetime.now(UTC),
    )
    src_id, _ = await repo.ingest_raw_source(src)
    sid = await repo.create_research_session(ResearchSession(topic_id=topic.id, mode="standard"))
    await repo.add_finding(
        ResearchFinding(session_id=sid, persona="academic", raw_source_id=src_id, summary="s")
    )
    await _compile_article(repo, home, topic, "Body with no citations section.")

    findings = await WikiLinter(repo).lint()

    missing = [f for f in findings if f.kind == "missing_citation"]
    assert len(missing) == 1
    assert missing[0].topic_slug == "cited"


async def test_missing_citation_not_flagged_when_no_sources(env) -> None:
    repo, home = env
    topic = await _make_topic(repo, "lonely", "Lonely Topic")
    await _compile_article(repo, home, topic, "No sources contributed to this one.")

    findings = await WikiLinter(repo).lint()

    assert [f for f in findings if f.kind == "missing_citation"] == []


async def test_missing_citation_not_flagged_when_citations_exist(env) -> None:
    repo, home = env
    topic = await _make_topic(repo, "cited2", "Cited Topic 2")
    assert topic.id is not None
    src = RawSource(
        content_hash="s2",
        source_type=SourceType.TEXT,
        title="src",
        text="source text",
        fetched_at=datetime.now(UTC),
    )
    src_id, _ = await repo.ingest_raw_source(src)
    sid = await repo.create_research_session(ResearchSession(topic_id=topic.id, mode="standard"))
    await repo.add_finding(
        ResearchFinding(session_id=sid, persona="academic", raw_source_id=src_id, summary="s")
    )
    article = await _compile_article(repo, home, topic, "Body [1].")
    assert article.id is not None
    await repo.insert_citation(article.id, "claim", src_id, "quote")

    findings = await WikiLinter(repo).lint()

    assert [f for f in findings if f.kind == "missing_citation"] == []


async def test_orphan_finding_for_unlinked_topics(env) -> None:
    repo, home = env
    a = await _make_topic(repo, "orphan-a", "Orphan A")
    b = await _make_topic(repo, "orphan-b", "Orphan B")
    await _compile_article(repo, home, a, "No links here.")
    await _compile_article(repo, home, b, "Also no links here.")

    findings = await WikiLinter(repo).lint()

    orphans = {f.topic_slug for f in findings if f.kind == "orphan"}
    assert {"orphan-a", "orphan-b"} <= orphans


async def test_no_orphan_when_linked_from_another_article(env) -> None:
    repo, home = env
    a = await _make_topic(repo, "link-a", "Link A")
    b = await _make_topic(repo, "link-b", "Link B")
    await _compile_article(repo, home, a, "See [[link-b|Link B]].")
    await _compile_article(repo, home, b, "No links here.")

    findings = await WikiLinter(repo).lint()

    orphans = {f.topic_slug for f in findings if f.kind == "orphan"}
    assert "link-b" not in orphans
    assert "link-a" in orphans  # nothing links back to a


async def test_self_link_does_not_prevent_orphan_finding(env) -> None:
    repo, home = env
    topic = await _make_topic(repo, "self", "Self Topic")
    await _compile_article(repo, home, topic, "See [[self|Self Topic]] (self-reference).")

    findings = await WikiLinter(repo).lint()

    orphans = {f.topic_slug for f in findings if f.kind == "orphan"}
    assert "self" in orphans


async def test_stale_confidence_finding_for_never_researched_topic(env) -> None:
    repo, home = env
    topic = await _make_topic(repo, "stale", "Stale Topic")  # last_researched_at is None
    await _compile_article(repo, home, topic, "Body")

    findings = await WikiLinter(repo).lint(now=datetime.now(UTC))

    stale = [f for f in findings if f.kind == "stale_confidence" and f.topic_slug == "stale"]
    assert len(stale) == 1


async def test_topic_without_article_is_skipped_entirely(env) -> None:
    repo, home = env
    await _make_topic(repo, "uncompiled", "Uncompiled Topic")  # never compiled -> no article

    findings = await WikiLinter(repo).lint()

    assert all(f.topic_slug != "uncompiled" for f in findings)


async def test_fix_removes_broken_wikilink_markup_from_db_and_disk(env) -> None:
    repo, home = env
    topic = await _make_topic(repo, "real", "Real Topic")
    await _compile_article(repo, home, topic, "See [[ghost|Ghost Topic]] for more.")

    linter = WikiLinter(repo, home=home)
    findings = await linter.lint()
    broken = [f for f in findings if f.kind == "broken_wikilink"]
    assert len(broken) == 1

    fixed_count = await linter.fix(broken)

    assert fixed_count == 1
    assert topic.id is not None
    latest = await repo.latest_article_for_topic(topic.id)
    assert latest is not None
    assert "[[ghost" not in latest.body_md
    assert "Ghost Topic" in latest.body_md
    on_disk = (home / latest.path).read_text(encoding="utf-8")
    assert "[[ghost" not in on_disk
    assert "Ghost Topic" in on_disk


async def test_fix_without_home_updates_db_only(env) -> None:
    repo, home = env
    topic = await _make_topic(repo, "real2", "Real Topic 2")
    await _compile_article(repo, home, topic, "See [[ghost2|Ghost Two]] for more.")

    linter = WikiLinter(repo)  # no home passed
    findings = await linter.lint()
    broken = [f for f in findings if f.kind == "broken_wikilink"]

    fixed_count = await linter.fix(broken)

    assert fixed_count == 1
    assert topic.id is not None
    latest = await repo.latest_article_for_topic(topic.id)
    assert latest is not None
    assert "[[ghost2" not in latest.body_md


async def test_fix_ignores_non_broken_wikilink_findings(env) -> None:
    repo, home = env
    topic = await _make_topic(repo, "orphan-only", "Orphan Only")
    await _compile_article(repo, home, topic, "No links here.")

    linter = WikiLinter(repo, home=home)
    findings = await linter.lint()
    orphans = [f for f in findings if f.kind == "orphan"]
    assert orphans

    fixed_count = await linter.fix(orphans)

    assert fixed_count == 0

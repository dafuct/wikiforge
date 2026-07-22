"""Direct topic<->source attachment (topic_sources): the internal-source compile bridge.

A raw source could previously belong to a topic only through a research session
(web-search findings). These tests pin the direct-attach path that lets an
ingested/internal source reach compilation with zero LLM spend.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.compile.compiler import Compiler
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import ParsedResult
from wikiforge.models.domain import RawSource, ResearchFinding, ResearchSession, Topic
from wikiforge.models.enums import SourceType, Volatility
from wikiforge.models.schemas import CompiledArticle
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


@pytest.fixture
async def repo(wiki_home: Path):
    db = await Database.open(wiki_home, dim=8)
    await db.init_schema()
    yield Repository(db)
    await db.close()


def _bare_source(hash_: str) -> RawSource:
    """An ingested source with no session and no finding — invisible to a topic today."""
    return RawSource(
        content_hash=hash_,
        source_type=SourceType.FILE,
        title=f"src-{hash_}",
        text="internal content",
        fetched_at=datetime.now(UTC),
    )


async def test_attached_source_is_visible_to_topic(repo: Repository) -> None:
    tid = await repo.upsert_topic(Topic(slug="internal", title="Internal"))
    src_id, _ = await repo.ingest_raw_source(_bare_source("h1"))
    # Precondition: a bare ingested source is invisible to the topic.
    assert await repo.raw_sources_for_topic(tid) == []
    newly = await repo.attach_source_to_topic(tid, src_id)
    assert newly is True
    sources = await repo.raw_sources_for_topic(tid)
    assert [s.id for s in sources] == [src_id]


async def test_attach_is_idempotent(repo: Repository) -> None:
    tid = await repo.upsert_topic(Topic(slug="t", title="T"))
    src_id, _ = await repo.ingest_raw_source(_bare_source("h1"))
    assert await repo.attach_source_to_topic(tid, src_id) is True
    assert await repo.attach_source_to_topic(tid, src_id) is False  # already attached
    sources = await repo.raw_sources_for_topic(tid)
    assert [s.id for s in sources] == [src_id]  # still exactly one


async def test_attach_dedups_with_research_linked_source(repo: Repository) -> None:
    tid = await repo.upsert_topic(Topic(slug="t", title="T"))
    src_id, _ = await repo.ingest_raw_source(_bare_source("h1"))
    # Reach the same source via a research session/finding AND a direct attach.
    sid = await repo.create_research_session(ResearchSession(topic_id=tid, mode="standard"))
    await repo.add_finding(
        ResearchFinding(session_id=sid, persona="academic", raw_source_id=src_id, summary="s")
    )
    await repo.attach_source_to_topic(tid, src_id)
    sources = await repo.raw_sources_for_topic(tid)
    assert [s.id for s in sources] == [src_id]  # SELECT DISTINCT collapses the two paths


async def test_topics_for_source_reverse_lookup(repo: Repository) -> None:
    t1 = await repo.upsert_topic(Topic(slug="a", title="A"))
    t2 = await repo.upsert_topic(Topic(slug="b", title="B"))
    src_id, _ = await repo.ingest_raw_source(_bare_source("h1"))
    await repo.attach_source_to_topic(t2, src_id)
    await repo.attach_source_to_topic(t1, src_id)
    assert await repo.topics_for_source(src_id) == sorted([t1, t2])


async def test_init_schema_adds_topic_sources_to_existing_db(repo: Repository) -> None:
    # Simulate a wiki created before topic_sources existed: drop the table, then
    # let init_schema re-add it (CREATE TABLE IF NOT EXISTS is additive on reopen).
    await repo._db.execute("DROP TABLE topic_sources")
    await repo._db.init_schema()
    tid = await repo.upsert_topic(Topic(slug="t", title="T"))
    src_id, _ = await repo.ingest_raw_source(_bare_source("h1"))
    assert await repo.attach_source_to_topic(tid, src_id) is True


class _CompileFakeLLM:
    """Synthesizes an article citing a given source hash. ``complete`` is a tripwire:
    the compiler must never take the web-search path."""

    def __init__(self, cite_hash: str) -> None:
        self.calls = 0
        self.user: str | None = None
        self._cite = cite_hash

    async def parse(
        self, purpose, system, user, *, tier=None, schema=None, topic_id=None, session_id=None
    ):
        self.calls += 1
        self.user = user
        from wikiforge.models.schemas import ClaimCitation

        art = CompiledArticle(
            title="Internal",
            body="Synthesized from the internal source [1]",
            citations=[ClaimCitation(claim="internal claim", source_id=self._cite, quote="q")],
            conflicts=[],
            open_questions=[],
            wikilinks=[],
            source_ids=[self._cite],
            distinct_domains=1,
            distinct_personas=0,
            source_dates=["2026-07-22"],
            evidence_strength=0.5,
        )
        return ParsedResult(parsed=art, input_tokens=0, output_tokens=0, model="fake")

    async def complete(self, *a, **k):
        raise AssertionError("compile must not web-search (complete() called)")


class _FakeEmbedder:
    @property
    def dim(self) -> int:
        return 8

    @property
    def model(self) -> str:
        return "fake"

    @property
    def provider_name(self) -> str:
        return "fake"

    async def embed(self, texts, *, kind="passage"):
        return [[0.1] * 8 for _ in texts]


async def test_attached_internal_file_compiles_and_cites_itself_without_web(
    repo: Repository, wiki_home: Path
) -> None:
    write_default_config(wiki_home, wiki_name="x")
    tid = await repo.upsert_topic(
        Topic(slug="internal", title="Internal", volatility=Volatility.LOW, stale_after_days=365)
    )
    src = RawSource(
        content_hash="internal-hash",
        source_type=SourceType.FILE,
        title="dev-log.md",
        text="internal dev log content",
        fetched_at=datetime.now(UTC),
    )
    src_id, _ = await repo.ingest_raw_source(src)
    await repo.attach_source_to_topic(tid, src_id)  # the ONLY link — no session, no finding

    llm = _CompileFakeLLM(cite_hash="internal-hash")
    compiler = Compiler(llm, _FakeEmbedder(), repo, load_config(wiki_home), wiki_home)
    topic = await repo.get_topic("internal")
    assert topic is not None
    article = await compiler.compile_topic(topic, force=True)

    assert article is not None
    # No research session was ever created — the internal path spent nothing on web search.
    assert await repo._db.fetchall("SELECT id FROM research_sessions") == []
    assert llm.calls == 1  # exactly one synthesis call, no research/normalize fan-out
    # The article cites the attached internal source by its raw_source id — not a URL.
    cites = await repo._db.fetchall("SELECT raw_source_id FROM citations")
    assert [c["raw_source_id"] for c in cites] == [src_id]
    # And the synthesis actually saw the internal source text.
    assert "internal dev log content" in (llm.user or "")

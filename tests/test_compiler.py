"""Compiler: writes article + citations + conflicts + markdown; incremental skip/force."""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.compile.compiler import Compiler
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import ParsedResult
from wikiforge.models.domain import RawSource, ResearchFinding, ResearchSession, Topic
from wikiforge.models.enums import SourceType, Volatility
from wikiforge.models.schemas import ClaimCitation, CompiledArticle, ConflictOut
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class FakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def parse(
        self, purpose, system, user, *, tier=None, schema=None, topic_id=None, session_id=None
    ):
        self.calls += 1
        art = CompiledArticle(
            title="Topic",
            body="Synthesized body [1]",
            citations=[ClaimCitation(claim="c", source_id="s1", quote="q")],
            conflicts=[ConflictOut(claim="x", nature="disagree", source_ids=["s1", "s2"])],
            open_questions=["oq"],
            wikilinks=[],
            source_ids=["s1", "s2"],
            distinct_domains=2,
            distinct_personas=2,
            source_dates=["2026-01-01"],
            evidence_strength=0.7,
        )
        return ParsedResult(parsed=art, input_tokens=0, output_tokens=0, model="claude-sonnet-5")

    async def complete(self, *a, **k):  # unused by compiler
        raise NotImplementedError


class FakeEmbedder:
    @property
    def dim(self) -> int:
        return 4

    @property
    def model(self) -> str:
        return "fake"

    @property
    def provider_name(self) -> str:
        return "fake"

    async def embed(self, texts):
        return [[1.0, 0.0, 0.0, 0.0] for _ in texts]


@pytest.fixture
async def env(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    (wiki_home / "topics").mkdir(exist_ok=True)
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    tid = await repo.upsert_topic(
        Topic(slug="topic", title="Topic", volatility=Volatility.LOW, stale_after_days=365)
    )
    src = RawSource(
        content_hash="s1",
        source_type=SourceType.TEXT,
        title="src",
        text="source text",
        fetched_at=datetime.now(UTC),
    )
    src_id, _ = await repo.ingest_raw_source(src)
    # Link the source to the topic via a research session + finding, so
    # raw_sources_for_topic(tid) returns it and the topic can compile.
    sid = await repo.create_research_session(ResearchSession(topic_id=tid, mode="standard"))
    await repo.add_finding(
        ResearchFinding(session_id=sid, persona="academic", raw_source_id=src_id, summary="s")
    )
    yield cfg, repo, tid, wiki_home
    await db.close()


async def test_compile_writes_article_and_markdown(env) -> None:
    cfg, repo, tid, home = env
    compiler = Compiler(FakeLLM(), FakeEmbedder(), repo, cfg, home)
    topic = await repo.get_topic("topic")
    article = await compiler.compile_topic(topic, force=True)
    assert article is not None
    md_path = home / "topics" / "topic" / "wiki" / "topic.md"
    assert md_path.exists()
    assert "## Contested" in md_path.read_text(encoding="utf-8")
    latest = await repo.latest_article_for_topic(tid)
    assert latest is not None and 0.0 <= latest.confidence <= 1.0

    import json

    rows = await repo._db.fetchall("SELECT source_ids FROM conflicts")
    assert len(rows) == 1
    stored_ids = json.loads(rows[0]["source_ids"])
    assert all(
        isinstance(x, int) for x in stored_ids
    )  # resolved to raw_source ids, not model strings
    assert len(stored_ids) == 1  # "s1" resolved; "s2" (not a stored source) dropped


async def test_recompile_drops_old_version_chunks(env) -> None:
    cfg, repo, tid, home = env
    compiler = Compiler(FakeLLM(), FakeEmbedder(), repo, cfg, home)
    topic = await repo.get_topic("topic")
    await compiler.compile_topic(topic, force=True)  # version 1
    await compiler.compile_topic(topic, force=True)  # version 2 (new article id)
    distinct = await repo._db.fetchall(
        "SELECT COUNT(DISTINCT owner_id) AS n FROM chunks WHERE owner_type='article'"
    )
    assert distinct[0]["n"] == 1  # only the latest version's chunks remain indexed
    art_chunks = await repo._db.fetchall(
        "SELECT COUNT(*) AS c FROM chunks WHERE owner_type='article'"
    )
    vecs = await repo._db.fetchall("SELECT COUNT(*) AS c FROM chunks_vec")
    assert vecs[0]["c"] == art_chunks[0]["c"]  # no orphan vectors after the version swap


async def test_incremental_skip_and_force(env) -> None:
    cfg, repo, tid, home = env
    llm = FakeLLM()
    compiler = Compiler(llm, FakeEmbedder(), repo, cfg, home)
    topic = await repo.get_topic("topic")
    first = await compiler.compile_topic(topic, force=True)
    assert first is not None and llm.calls == 1
    # unchanged inputs -> digest matches -> skipped, no new LLM call
    second = await compiler.compile_topic(topic, force=False)
    assert second is None and llm.calls == 1
    # force -> recompiles
    third = await compiler.compile_topic(topic, force=True)
    assert third is not None and llm.calls == 2

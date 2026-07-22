"""Dev-event → topic routing at consolidation: match aged events to subject topics.

A consolidated dev event is matched (local embedding, zero LLM) to its most
relevant compiled topic and attached via topic_sources, so that topic's article
cites the internal event on next compile. These tests pin the matching gate and
the consolidate integration; all deterministic with a keyword→vector fake embedder.
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from wikiforge.compile.compiler import Compiler
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.llm.provider import ParsedResult
from wikiforge.models.domain import Article, RawSource, Topic
from wikiforge.models.enums import SourceType, TopicStatus
from wikiforge.models.schemas import ClaimCitation, CompiledArticle
from wikiforge.ops.consolidate import (
    ConsolidateStats,
    PeriodRollup,
    _route_event_topics,
    consolidate_dev_log,
    routed_clause,
)
from wikiforge.search.index import index_owner
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository

_NOW = datetime(2026, 7, 22, tzinfo=UTC)
_OLD = datetime(2026, 6, 1, tzinfo=UTC)  # older than min_age_days (14) before _NOW

# Unit basis-ish vectors (all norm 1, so dot == cosine). First keyword in a text wins.
_VECS: dict[str, list[float]] = {
    "close": [0.9805, 0.1961, 0.0, 0.0],  # cosine with alpha ≈ 0.9805 (≥ 0.82)
    "near": [0.8, 0.6, 0.0, 0.0],  # cosine with alpha = 0.80 (< 0.82)
    "alpha": [1.0, 0.0, 0.0, 0.0],
    "beta": [0.0, 1.0, 0.0, 0.0],
}


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

    def _vec(self, text: str) -> list[float]:
        low = text.lower()
        for kw, v in _VECS.items():
            if kw in low:
                return v
        return [0.0, 0.0, 0.0, 1.0]

    async def embed(self, texts: list[str], *, kind: str = "passage") -> list[list[float]]:
        return [self._vec(t) for t in texts]


@pytest.fixture
async def env(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    (wiki_home / "topics").mkdir(exist_ok=True)
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    yield Repository(db), FakeEmbedder(), cfg
    await db.close()


async def _seed_topic(
    repo: Repository, emb: FakeEmbedder, slug: str, text: str, *, archived: bool = False
) -> int:
    """Create a topic with one compiled article chunk whose vector is _vec(text)."""
    tid = await repo.upsert_topic(
        Topic(
            slug=slug,
            title=slug,
            status=TopicStatus.ARCHIVED if archived else TopicStatus.ACTIVE,
        )
    )
    art_id = await repo.insert_article(
        Article(
            topic_id=tid,
            slug=slug,
            title=slug,
            body_md=text,
            path=f"topics/{slug}/wiki/{slug}.md",
            confidence=0.5,
            compile_digest=f"d-{slug}",
            version=1,
        )
    )
    await index_owner(repo, emb, owner_type="article", owner_id=art_id, text=text)
    return tid


async def _dev_event(repo: Repository, text: str) -> RawSource:
    src = RawSource(
        content_hash=f"h-{text}",
        source_type=SourceType.DEV_EVENT,
        title="dev event",
        text=text,
        fetched_at=datetime.now(UTC),
        provenance={"type": "change", "label": "development-log"},
    )
    sid, _ = await repo.ingest_raw_source(src)
    got = await repo.get_raw_source_by_id(sid)
    assert got is not None
    return got


async def test_routes_event_to_nearest_topic(env) -> None:
    repo, emb, cfg = env
    a = await _seed_topic(repo, emb, "alpha", "alpha content")
    await _seed_topic(repo, emb, "beta", "beta content")
    devlog = await repo.upsert_topic(Topic(slug="development-log", title="Development log"))
    ev = await _dev_event(repo, "alpha work")
    assert await _route_event_topics(repo, emb, ev, cfg=cfg, devlog_topic_id=devlog) == [a]


async def test_excludes_devlog_and_archived_even_if_similar(env) -> None:
    repo, emb, cfg = env
    a = await _seed_topic(repo, emb, "alpha", "alpha content")
    devlog = await _seed_topic(repo, emb, "development-log", "alpha devlog content")
    await _seed_topic(repo, emb, "arch", "alpha archived content", archived=True)
    ev = await _dev_event(repo, "alpha work")
    # Both dev-log and archived article chunks are cosine 1.0 with the event, yet excluded.
    assert await _route_event_topics(repo, emb, ev, cfg=cfg, devlog_topic_id=devlog) == [a]


async def test_below_threshold_routes_nowhere(env) -> None:
    repo, emb, cfg = env
    await _seed_topic(repo, emb, "alpha", "alpha content")
    devlog = await repo.upsert_topic(Topic(slug="development-log", title="Development log"))
    ev = await _dev_event(repo, "near miss")  # cosine 0.80 with alpha < 0.82 gate
    assert await _route_event_topics(repo, emb, ev, cfg=cfg, devlog_topic_id=devlog) == []


async def test_route_max_topics_caps(env) -> None:
    repo, emb, cfg = env
    a = await _seed_topic(repo, emb, "alpha", "alpha content")
    c = await _seed_topic(repo, emb, "close", "close content")  # cosine 0.9805 with the event
    devlog = await repo.upsert_topic(Topic(slug="development-log", title="Development log"))
    ev = await _dev_event(repo, "alpha work")  # query vec [1,0,0,0]

    one = await _route_event_topics(repo, emb, ev, cfg=cfg, devlog_topic_id=devlog)
    assert one == [a]  # top-1: cosine 1.0 (alpha) beats 0.9805 (close)

    cfg2 = cfg.model_copy(
        update={"consolidate": cfg.consolidate.model_copy(update={"route_max_topics": 2})}
    )
    two = await _route_event_topics(repo, emb, ev, cfg=cfg2, devlog_topic_id=devlog)
    assert two == [a, c]


# --- Cycle 2: integration into consolidate_dev_log --------------------------


class _RollupLLM:
    """Cheap-tier rollup stub; complete() is a tripwire (consolidate must not web-search)."""

    async def parse(
        self, purpose, system, user, *, tier=None, schema=None, topic_id=None, session_id=None
    ):
        return ParsedResult(
            parsed=PeriodRollup(markdown="- rolled up"),
            input_tokens=0,
            output_tokens=0,
            model="fake",
        )

    async def complete(self, *a, **k):
        raise AssertionError("consolidate must not web-search")


class _CompilerLLM:
    """Synthesizes an article citing a given source hash (for the compile capstone)."""

    def __init__(self, cite_hash: str) -> None:
        self._cite = cite_hash

    async def parse(
        self, purpose, system, user, *, tier=None, schema=None, topic_id=None, session_id=None
    ):
        art = CompiledArticle(
            title="Alpha",
            body="From the internal event [1]",
            citations=[ClaimCitation(claim="c", source_id=self._cite, quote="q")],
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
        raise AssertionError("compile must not web-search")


async def _aged_dev_event(repo: Repository, text: str) -> RawSource:
    ts = _OLD.strftime("%Y-%m-%dT%H:%M:%SZ")
    src = RawSource(
        content_hash=f"h-{text}",
        source_type=SourceType.DEV_EVENT,
        title="dev event",
        text=text,
        fetched_at=_OLD,
        provenance={"type": "change", "label": "development-log", "ts": ts},
    )
    sid, _ = await repo.ingest_raw_source(src)
    got = await repo.get_raw_source_by_id(sid)
    assert got is not None
    return got


async def test_consolidate_routes_aged_event_to_topic(env, wiki_home: Path) -> None:
    repo, emb, cfg = env
    a = await _seed_topic(repo, emb, "alpha", "alpha content")
    ev = await _aged_dev_event(repo, "alpha work")

    stats = await consolidate_dev_log(repo, emb, _RollupLLM(), cfg, wiki_home, now=_NOW)

    assert stats.routed == 1
    assert ev.id in [s.id for s in await repo.raw_sources_for_topic(a)]  # attached, compile-ready
    got = await repo.get_raw_source_by_id(ev.id)
    assert got is not None and got.provenance.get("consolidated")  # marked, left recall


async def test_consolidate_route_disabled(env, wiki_home: Path) -> None:
    repo, emb, cfg = env
    a = await _seed_topic(repo, emb, "alpha", "alpha content")
    cfg2 = cfg.model_copy(
        update={"consolidate": cfg.consolidate.model_copy(update={"route": False})}
    )
    await _aged_dev_event(repo, "alpha work")

    stats = await consolidate_dev_log(repo, emb, _RollupLLM(), cfg2, wiki_home, now=_NOW)

    assert stats.routed == 0
    assert await repo.raw_sources_for_topic(a) == []  # nothing attached
    assert stats.events == 1  # rollup still ran


async def test_consolidate_routing_is_idempotent(env, wiki_home: Path) -> None:
    repo, emb, cfg = env
    await _seed_topic(repo, emb, "alpha", "alpha content")
    await _aged_dev_event(repo, "alpha work")
    first = await consolidate_dev_log(repo, emb, _RollupLLM(), cfg, wiki_home, now=_NOW)
    second = await consolidate_dev_log(repo, emb, _RollupLLM(), cfg, wiki_home, now=_NOW)
    assert (first.routed, second.routed) == (1, 0)  # already consolidated -> not re-routed


async def test_routed_event_compiles_into_cited_article(env, wiki_home: Path) -> None:
    repo, emb, cfg = env
    await _seed_topic(repo, emb, "alpha", "alpha content")
    ev = await _aged_dev_event(repo, "alpha work")
    await consolidate_dev_log(repo, emb, _RollupLLM(), cfg, wiki_home, now=_NOW)

    topic = await repo.get_topic("alpha")
    assert topic is not None
    compiler = Compiler(_CompilerLLM(cite_hash=ev.content_hash), emb, repo, cfg, wiki_home)
    article = await compiler.compile_topic(topic, force=True)

    assert article is not None
    cites = await repo._db.fetchall("SELECT raw_source_id FROM citations")
    assert [c["raw_source_id"] for c in cites] == [ev.id]  # the routed dev event is cited


def test_routed_clause_only_when_routed() -> None:
    assert routed_clause(ConsolidateStats(periods=1, events=5, routed=2)) == (
        ", routed 2 event(s) to topics"
    )
    assert routed_clause(ConsolidateStats(periods=1, events=5, routed=0)) == ""

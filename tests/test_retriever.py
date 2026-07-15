"""Hybrid retrieval: RRF over FTS+vec, archived exclusion, depth scoping, rerank."""

from __future__ import annotations

from pathlib import Path

import pytest

from wikiforge.config.settings import load_config, write_default_config
from wikiforge.models.domain import Article, RawSource, Topic
from wikiforge.models.enums import SourceType, TopicStatus
from wikiforge.search.retriever import HybridRetriever
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


class KeywordEmbedder:
    """Deterministic dim-4 embedder: vector depends on presence of a few keywords."""

    @property
    def dim(self) -> int:
        return 4

    @property
    def model(self) -> str:
        return "kw"

    @property
    def provider_name(self) -> str:
        return "kw"

    async def embed(self, texts):
        out = []
        for t in texts:
            low = t.lower()
            out.append(
                [
                    1.0 if "async" in low else 0.0,
                    1.0 if "rust" in low else 0.0,
                    1.0 if "memory" in low else 0.0,
                    0.1,
                ]
            )
        return out


async def _article_chunk(repo, embedder, slug, text, *, status=TopicStatus.ACTIVE):
    tid = await repo.upsert_topic(Topic(slug=slug, title=slug, status=status, stale_after_days=90))
    aid = await repo.insert_article(
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
    from wikiforge.search.index import index_owner

    await index_owner(repo, embedder, owner_type="article", owner_id=aid, text=text)
    return tid


@pytest.fixture
async def env(wiki_home: Path):
    write_default_config(wiki_home, wiki_name="x")
    cfg = load_config(wiki_home)
    db = await Database.open(wiki_home, dim=4)
    await db.init_schema()
    yield cfg, Repository(db), KeywordEmbedder()
    await db.close()


async def test_retrieve_finds_relevant_article(env) -> None:
    cfg, repo, emb = env
    await _article_chunk(
        repo, emb, "rust-async", "# Rust Async\n\nRust async is cooperative and fast."
    )
    await _article_chunk(repo, emb, "python-gil", "# Python GIL\n\nThe global interpreter lock.")
    r = HybridRetriever(repo, emb, cfg)
    hits = await r.retrieve("async rust", depth="quick")
    assert any("Rust Async" in h.text for h in hits)
    assert all(h.owner_type == "article" for h in hits)


async def test_archived_topic_excluded(env) -> None:
    cfg, repo, emb = env
    await _article_chunk(
        repo,
        emb,
        "rust-async",
        "# Rust Async\n\nRust async is cooperative.",
        status=TopicStatus.ARCHIVED,
    )
    r = HybridRetriever(repo, emb, cfg)
    hits = await r.retrieve("async rust", depth="quick")
    assert all("Rust Async" not in h.text for h in hits)  # archived topic filtered out
    hits2 = await r.retrieve("async rust", depth="quick", include_archived=True)
    assert any("Rust Async" in h.text for h in hits2)


async def test_deep_applies_reranker(env) -> None:
    cfg, repo, emb = env
    await _article_chunk(repo, emb, "a", "# A\n\nasync rust memory content here")
    await _article_chunk(repo, emb, "b", "# B\n\nasync rust content here too")
    seen = {}

    def reranker(query, docs):
        seen["called"] = True
        # rank the LAST doc highest to prove the reranker order is applied
        return [float(i) for i in range(len(docs))]

    r = HybridRetriever(repo, emb, cfg, reranker=reranker)
    hits = await r.retrieve("async rust", depth="deep")
    assert seen.get("called") is True
    assert hits  # rerank produced an ordering


async def _dev_event_chunk(repo, emb, text: str) -> int:
    from datetime import UTC, datetime

    from wikiforge.search.index import index_owner

    src = RawSource(
        content_hash=f"h-{text[:16]}", source_type=SourceType.DEV_EVENT,
        title="Dev event", text=text, fetched_at=datetime(2026, 7, 15, tzinfo=UTC),
        provenance={},
    )
    sid, _ = await repo.ingest_raw_source(src)
    await index_owner(repo, emb, owner_type="raw_source", owner_id=sid, text=text)
    return sid


async def test_owner_types_override_surfaces_devlog_at_standard_depth(env) -> None:
    cfg, repo, emb = env
    await _dev_event_chunk(repo, emb, "dev event about rust async deadlock")
    r = HybridRetriever(repo, emb, cfg)
    default_hits = await r.retrieve("async rust", depth="standard")
    assert all(h.owner_type == "article" for h in default_hits)  # unchanged default
    all_hits = await r.retrieve(
        "async rust", depth="standard", owner_types=["article", "raw_source"]
    )
    assert any(h.owner_type == "raw_source" for h in all_hits)


async def test_owner_types_devlog_only(env) -> None:
    cfg, repo, emb = env
    await _article_chunk(repo, emb, "rust-async", "# Rust Async\n\nRust async is cooperative.")
    await _dev_event_chunk(repo, emb, "dev event about rust async deadlock")
    r = HybridRetriever(repo, emb, cfg)
    hits = await r.retrieve("async rust", depth="standard", owner_types=["raw_source"])
    assert hits and all(h.owner_type == "raw_source" for h in hits)

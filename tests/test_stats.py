"""Stats aggregation over a seeded DB (no network)."""

from __future__ import annotations

from pathlib import Path

from wikiforge.activity.cost import CostTracker
from wikiforge.activity.stats import StatsService, WikiStats
from wikiforge.config.settings import load_config, write_default_config
from wikiforge.models.domain import Article, Topic
from wikiforge.storage.db import Database
from wikiforge.storage.repository import Repository


async def _seed(home: Path) -> Repository:
    write_default_config(home, wiki_name="x")
    cfg = load_config(home)
    db = await Database.open(home, dim=4)
    await db.init_schema()
    repo = Repository(db)
    tid = await repo.upsert_topic(Topic(slug="t", title="T", stale_after_days=90))
    await repo.insert_article(
        Article(
            topic_id=tid,
            slug="t",
            title="T",
            body_md="body",
            path="topics/t/wiki/t.md",
            confidence=0.5,
            compile_digest="d",
            version=1,
        )
    )
    tracker = CostTracker(repo, cfg)
    await tracker.record(
        provider="anthropic",
        model="claude-sonnet-5",
        purpose="compile",
        input_tokens=1000,
        output_tokens=500,
    )
    return repo


async def test_compute_counts_and_costs(wiki_home: Path) -> None:
    repo = await _seed(wiki_home)
    stats = await StatsService(repo).compute()
    assert isinstance(stats, WikiStats)
    assert stats.topics == 1
    assert stats.articles == 1
    assert stats.raw_sources == 0
    assert stats.total_cost_usd > 0.0
    assert "claude-sonnet-5" in stats.cost_by_model
    assert stats.since is None and stats.calls_since is None


async def test_compute_since_window_counts_calls(wiki_home: Path) -> None:
    repo = await _seed(wiki_home)
    # A far-past lower bound includes the one recorded call.
    stats = await StatsService(repo).compute(since="2000-01-01")
    assert stats.since == "2000-01-01"
    assert stats.calls_since == 1
    assert stats.cost_since_usd is not None and stats.cost_since_usd > 0.0
    # A far-future lower bound excludes it.
    future = await StatsService(repo).compute(since="2999-01-01")
    assert future.calls_since == 0
    assert future.cost_since_usd == 0.0
